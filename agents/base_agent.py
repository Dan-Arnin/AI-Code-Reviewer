# coding: utf-8
"""
agents/base_agent.py
Abstract base class for all code-review agents.

Each agent:
  - Receives the full DiffResult.
  - Builds a specialised prompt using its rules from BEST_PRACTICES.
  - Calls the AI client's chat() method (OCI or Claude, same interface).
  - Returns a structured AgentResult.

Findings are split at parse-time:
  - CRITICAL / HIGH  → ``findings``   (blocking issues, shown first; capped at 10)
  - MEDIUM / LOW / INFO → ``suggestions`` (shown separately in the Suggestions tab)
"""

import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from config import BEST_PRACTICES, SUGGESTION_PRACTICES, MAX_DIFF_LINES_PER_CHUNK, runtime_config
from logger import get_logger

# Maximum blocking findings to surface per agent (keeps reports focused)
_MAX_BLOCKING_FINDINGS = 10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single issue raised by an agent."""
    severity: str        # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    category: str        # e.g. "Security", "Style"
    file_path: str       # File where the issue was found (empty = general)
    line_reference: str  # e.g. "L42" or a short description
    description: str     # What the problem is
    explanation: str     # Detailed explanation of why this is a problem
    suggestion: str      # How to fix it
    best_practice: str   # What best practice to follow


@dataclass
class AgentResult:
    """Aggregated output from a single agent run."""
    agent_name: str
    findings: List["Finding"] = field(default_factory=list)      # CRITICAL / HIGH only
    suggestions: List["Finding"] = field(default_factory=list)   # MEDIUM / LOW / INFO
    summary: str = ""
    raw_responses: List[str] = field(default_factory=list)
    had_errors: bool = False   # True if any AI call failed

    @property
    def severity_counts(self) -> dict:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings + self.suggestions:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class BaseReviewAgent(ABC):
    """
    Abstract agent that reviews code diffs against a set of best-practice rules.

    Subclasses must implement:
      - ``category_key``: key into BEST_PRACTICES dict.
      - ``agent_name``:   human-readable name.
      - ``extra_instructions`` (optional): additional prompt guidance.
    """

    category_key: str = ""
    agent_name: str = "Generic Agent"
    extra_instructions: str = ""

    def __init__(self, ai_client):
        """Accept any AI client that exposes a chat(prompt) -> str method."""
        self._client = ai_client
        self._log = get_logger(f"agents.{self.agent_name.lower().replace(' ', '_')}")

    @property
    def _rules(self) -> List[str]:
        """Critical rules only — finding these = CRITICAL/HIGH severity."""
        override_text = runtime_config.get(f"prompt_{self.category_key}")
        if override_text:
            return [line.strip() for line in override_text.splitlines() if line.strip()]
        return BEST_PRACTICES.get(self.category_key, [])

    @property
    def _suggestion_rules(self) -> List[str]:
        """Improvement rules — finding these = MEDIUM/LOW severity (Suggestions tab)."""
        return SUGGESTION_PRACTICES.get(self.category_key, [])

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def review(self, diff_result) -> AgentResult:
        """
        Run the agent against a :class:`DiffResult`.

        Returns:
            :class:`AgentResult` with all findings and summaries.
        """
        result = AgentResult(agent_name=self.agent_name)
        chunks = self._split_diff(diff_result.full_diff)
        total_chunks = len(chunks)

        self._log.info(
            "Starting review | %d rule(s) | diff split into %d chunk(s).",
            len(self._rules), total_chunks,
        )

        for i, chunk in enumerate(chunks, start=1):
            self._log.debug("Processing chunk %d/%d (length=%d chars).", i, total_chunks, len(chunk))

            # ── Critical pass (CRITICAL / HIGH only) ──────────────────────────
            prompt_critical = self._build_prompt(
                chunk, i, total_chunks, diff_result, mode="critical"
            )
            try:
                response = self._client.chat(prompt_critical)
                if response and response.strip():
                    result.raw_responses.append(response)
                    all_findings = self._parse_response(response)

                    blocking = [f for f in all_findings if f.severity in ("CRITICAL", "HIGH")]
                    result.findings.extend(blocking)

                    self._log.debug(
                        "Chunk %d/%d critical pass → %d blocking finding(s).",
                        i, total_chunks, len(blocking),
                    )
                else:
                    self._log.warning("Empty response on critical pass chunk %d/%d.", i, total_chunks)
                    result.had_errors = True

            except RuntimeError as exc:
                self._log.error(
                    "AI call failed on critical pass chunk %d/%d: %s", i, total_chunks, exc
                )
                result.raw_responses.append(f"[ERROR] {exc}")
                result.had_errors = True
            except Exception as exc:
                self._log.error(
                    "Unexpected error on critical pass chunk %d/%d: %s", i, total_chunks, exc,
                    exc_info=True,
                )
                result.raw_responses.append(f"[ERROR] Unexpected: {exc}")
                result.had_errors = True

            # ── Suggestion pass (MEDIUM / LOW only) ──────────────────────────
            if self._suggestion_rules:
                prompt_sug = self._build_prompt(
                    chunk, i, total_chunks, diff_result, mode="suggestions"
                )
                try:
                    sug_response = self._client.chat(prompt_sug)
                    if sug_response and sug_response.strip():
                        all_sug = self._parse_response(sug_response)
                        suggestions_found = [
                            f for f in all_sug
                            if f.severity not in ("CRITICAL", "HIGH")
                        ]
                        result.suggestions.extend(suggestions_found)
                        self._log.debug(
                            "Chunk %d/%d suggestion pass → %d suggestion(s).",
                            i, total_chunks, len(suggestions_found),
                        )
                except Exception as exc:
                    # Suggestion pass failures are non-fatal
                    self._log.debug("Suggestion pass failed for chunk %d/%d: %s", i, total_chunks, exc)

        total_findings = len(result.findings)
        total_suggestions = len(result.suggestions)

        # Cap blocking findings at the maximum to keep reports focused
        if len(result.findings) > _MAX_BLOCKING_FINDINGS:
            self._log.info(
                "Capping blocking findings from %d to %d for agent '%s'.",
                len(result.findings), _MAX_BLOCKING_FINDINGS, self.agent_name,
            )
            result.findings = result.findings[:_MAX_BLOCKING_FINDINGS]

        severity_summary = ", ".join(
            f"{v} {k}" for k, v in result.severity_counts.items() if v > 0
        ) or "none"

        self._log.info(
            "Review complete → %d blocking finding(s) | %d suggestion(s) [%s]%s",
            total_findings,
            total_suggestions,
            severity_summary,
            " | ⚠ some AI calls failed – results may be incomplete" if result.had_errors else "",
        )

        # Log first 400 chars of AI response at DEBUG level
        if result.raw_responses:
            last_resp = result.raw_responses[-1]
            if not last_resp.startswith("[ERROR]"):
                self._log.debug("Last AI response preview: %s …", last_resp[:400].replace("\n", " "))

        result.summary = self._build_summary(result)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _split_diff(self, full_diff: str) -> List[str]:
        """Split a large unified diff into chunks of at most MAX_DIFF_LINES_PER_CHUNK lines."""
        lines = full_diff.splitlines()
        if not lines:
            self._log.warning("Diff is empty – sending placeholder text to OCI.")
            return ["(no diff available)"]
        chunks = []
        for i in range(0, len(lines), MAX_DIFF_LINES_PER_CHUNK):
            chunks.append("\n".join(lines[i: i + MAX_DIFF_LINES_PER_CHUNK]))
        if len(chunks) > 1:
            self._log.warning(
                "Large diff detected (%d lines) → split into %d chunks of %d lines each.",
                len(lines), len(chunks), MAX_DIFF_LINES_PER_CHUNK,
            )
        return chunks

    def _build_prompt(
        self, diff_chunk: str, chunk_idx: int, total_chunks: int, diff_result,
        mode: str = "critical",
    ) -> str:
        """
        Build the prompt sent to the AI model.

        mode="critical"     → CRITICAL/HIGH only, strict "do not flag" list
        mode="suggestions"  → MEDIUM/LOW suggestions only
        """
        if mode == "suggestions":
            rules_text = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(self._suggestion_rules))
            return textwrap.dedent(f"""
                You are a senior software engineer reviewing a unified diff for code-quality improvements.
                Focus area: **{self.agent_name} – Suggestions Only**

                ## Improvement rules (MEDIUM / LOW severity only)
{rules_text}

                ## Context
                - Repository: {diff_result.metadata.repo_url}
                - Source branch: {diff_result.metadata.source_branch}
                - Target branch: {diff_result.metadata.target_branch}
                - Chunk {chunk_idx} of {total_chunks}

                ## STRICT INSTRUCTIONS
                - Only output findings with SEVERITY: MEDIUM or SEVERITY: LOW.
                - Do NOT flag missing try/catch, null checks, or runtime crashes — those are handled separately.
                - Keep each DESCRIPTION to one short sentence.
                - Cap your response at 6 findings maximum. Quality over quantity.

                ## Unified Diff
                ```diff
                {diff_chunk}
                ```

                ## Output format (repeat per finding)
                FINDING_START
                SEVERITY: <MEDIUM|LOW>
                FILE: <path or "general">
                LINE: <line or reference>
                DESCRIPTION: <one-line>
                EXPLANATION: <one sentence why>
                SUGGESTION: <one-line fix>
                BEST_PRACTICE: <rule violated>
                FINDING_END

                SUMMARY: <one sentence on {self.agent_name.lower()} improvement opportunities>

                If nothing to suggest: SUMMARY: No {self.agent_name.lower()} suggestions.
            """).strip()

        # ── Critical mode ────────────────────────────────────────────────────
        rules_text = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(self._rules))
        extra = (
            f"\nAdditional instructions:\n{self.extra_instructions}"
            if self.extra_instructions else ""
        )
        return textwrap.dedent(f"""
            You are a senior software engineer performing a strict code review.
            Focus area: **{self.agent_name} – Critical & High Issues Only**

            ## Rules to enforce (CRITICAL / HIGH severity only)
{rules_text}
{extra}

            ## Context
            - Repository: {diff_result.metadata.repo_url}
            - Source branch (MR): {diff_result.metadata.source_branch}
            - Target branch (prod): {diff_result.metadata.target_branch}
            - Chunk {chunk_idx} of {total_chunks}

            ## STRICT INSTRUCTIONS — read carefully before responding
            Only raise a finding if the code WILL or VERY LIKELY WILL:
              • Throw an unhandled exception / crash the process
              • Cause data loss or corruption
              • Allow SQL injection, RCE, or directory traversal
              • Cause an unhandled Promise rejection that crashes Node.js
              • Access a property on a value that is provably null/undefined

            DO NOT flag any of the following (skip them completely):
              ✗ Logging of user messages, LLM responses, or debug payloads
              ✗ Hardcoded file paths or OCI config paths (e.g. /home/.oci/config)
              ✗ Missing JSDoc, type hints, or inline comments
              ✗ Naming conventions, code style, or formatting issues
              ✗ Redundant computations or micro-optimisations (e.g. moment() in a sort)
              ✗ Missing input sanitisation UNLESS it directly enables injection attacks
              ✗ Hardcoded non-secret constants or URL strings
              ✗ Anything you would rate MEDIUM, LOW, or INFO — those belong in suggestions

            If in doubt, DO NOT raise the finding.
            Cap your response at 10 findings maximum.

            ## Unified Diff (chunk {chunk_idx}/{total_chunks})
            ```diff
            {diff_chunk}
            ```

            ## Required output format
            FINDING_START
            SEVERITY: <CRITICAL|HIGH>
            FILE: <file path or "general">
            LINE: <line number or short reference>
            DESCRIPTION: <one-line description of the problem>
            EXPLANATION: <why this will crash or break the code>
            SUGGESTION: <one-line fix>
            BEST_PRACTICE: <rule violated>
            FINDING_END

            After all findings output:
            SUMMARY: <one sentence on the {self.agent_name} health of this diff>

            If no critical/high issues found:
            SUMMARY: No {self.agent_name.lower()} blocking issues found.
        """).strip()

    @staticmethod
    def _extract_field(block: str, field_name: str) -> str:
        """Extract a named field value from a FINDING block string."""
        for line in block.splitlines():
            if line.strip().startswith(f"{field_name}:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _parse_response(self, response: str) -> List[Finding]:
        """Parse FINDING_START...FINDING_END blocks from the model response."""
        findings: List[Finding] = []
        blocks = response.split("FINDING_START")
        if len(blocks) == 1:
            # No structured blocks found — model deviated from the format
            self._log.debug(
                "No FINDING_START blocks in OCI response. "
                "Model either found no issues OR deviated from the required format. "
                "Full response logged at DEBUG level above."
            )
        for block in blocks[1:]:
            end_idx = block.find("FINDING_END")
            if end_idx == -1:
                self._log.warning(
                    "Found FINDING_START with no matching FINDING_END – skipping malformed block."
                )
                continue
            finding_block = block[:end_idx]

            severity = self._extract_field(finding_block, "SEVERITY").upper()
            if severity not in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
                self._log.debug(
                    "Unknown severity value '%s' in finding – defaulting to LOW.", severity
                )
                severity = "LOW"

            findings.append(Finding(
                severity=severity,
                category=self.agent_name,
                file_path=self._extract_field(finding_block, "FILE"),
                line_reference=self._extract_field(finding_block, "LINE"),
                description=self._extract_field(finding_block, "DESCRIPTION"),
                explanation=self._extract_field(finding_block, "EXPLANATION"),
                suggestion=self._extract_field(finding_block, "SUGGESTION"),
                best_practice=self._extract_field(finding_block, "BEST_PRACTICE"),
            ))
        return findings

    def _build_summary(self, result: AgentResult) -> str:
        """Extract the last SUMMARY line from raw responses."""
        for resp in reversed(result.raw_responses):
            if resp.startswith("[ERROR]"):
                continue
            for line in reversed(resp.splitlines()):
                if line.strip().startswith("SUMMARY:"):
                    return line.split(":", 1)[1].strip()
        if result.had_errors:
            return (
                "⚠ One or more OCI calls failed – results are incomplete. "
                "Check the logs/ directory for details."
            )
        counts = result.severity_counts
        total = sum(counts.values())
        return (
            f"{total} issue(s) found: "
            + ", ".join(f"{v} {k}" for k, v in counts.items() if v > 0)
            if total
            else f"No {self.agent_name.lower()} issues detected."
        )
