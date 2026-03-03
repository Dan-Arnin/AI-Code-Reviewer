# coding: utf-8
"""
agents/base_agent.py
Abstract base class for all code-review agents.

Each agent:
  - Receives the full DiffResult.
  - Builds a specialised prompt using its rules from BEST_PRACTICES.
  - Calls OCIGenAIClient.chat() (potentially in chunks for large diffs).
  - Returns a structured AgentResult.
"""

import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from config import BEST_PRACTICES, MAX_DIFF_LINES_PER_CHUNK
from oci_client import OCIGenAIClient
from logger import get_logger


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
    findings: List[Finding] = field(default_factory=list)
    summary: str = ""
    raw_responses: List[str] = field(default_factory=list)
    had_errors: bool = False   # True if any OCI call failed

    @property
    def severity_counts(self) -> dict:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for f in self.findings:
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

    def __init__(self, oci_client: OCIGenAIClient):
        self._client = oci_client
        self._rules: List[str] = BEST_PRACTICES.get(self.category_key, [])
        self._log = get_logger(f"agents.{self.agent_name.lower().replace(' ', '_')}")

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
            prompt = self._build_prompt(chunk, i, total_chunks, diff_result)

            try:
                response = self._client.chat(prompt)

                if not response or not response.strip():
                    self._log.warning(
                        "OCI returned an empty response for chunk %d/%d.\n"
                        "  WHAT WENT WRONG : The model produced no output. This can happen "
                        "due to content filtering, a model quota issue, or a transient API glitch.\n"
                        "  WHAT TO DO      : Retry the review. If it keeps happening, check OCI "
                        "service health at https://ocistatus.oraclecloud.com/ and verify your "
                        "token quota in the OCI Console under Generative AI → Limits.",
                        i, total_chunks,
                    )
                    result.raw_responses.append("[ERROR] OCI returned empty response.")
                    result.had_errors = True
                    continue

                result.raw_responses.append(response)
                findings = self._parse_response(response)
                result.findings.extend(findings)

                self._log.debug(
                    "Chunk %d/%d processed → %d finding(s) extracted.",
                    i, total_chunks, len(findings),
                )

            except RuntimeError as exc:
                # RuntimeError is already logged with context in oci_client.py
                self._log.error(
                    "OCI call failed for chunk %d/%d → skipping this chunk.\n"
                    "  WHAT WENT WRONG : %s\n"
                    "  WHAT TO DO      : See the detailed error above. Fix the OCI "
                    "credentials or network issue, then re-run the review.",
                    i, total_chunks, exc,
                )
                result.raw_responses.append(f"[ERROR] {exc}")
                result.had_errors = True

            except Exception as exc:
                self._log.error(
                    "Unexpected error in agent '%s' for chunk %d/%d.\n"
                    "  WHAT WENT WRONG : %s\n"
                    "  WHAT TO DO      : This is an unexpected internal error. Check "
                    "the full log file in the logs/ directory for the complete stack trace.",
                    self.agent_name, i, total_chunks, exc,
                    exc_info=True,   # prints full traceback to the log file
                )
                result.raw_responses.append(f"[ERROR] Unexpected: {exc}")
                result.had_errors = True

        total_findings = len(result.findings)
        severity_summary = ", ".join(
            f"{v} {k}" for k, v in result.severity_counts.items() if v > 0
        ) or "none"

        self._log.info(
            "Review complete → %d finding(s) [%s]%s",
            total_findings,
            severity_summary,
            " | ⚠ some OCI calls failed – results may be incomplete" if result.had_errors else "",
        )

        # Log first 400 chars of OCI response at DEBUG level so it's visible in the log file
        if result.raw_responses:
            last_resp = result.raw_responses[-1]
            if not last_resp.startswith("[ERROR]"):
                self._log.debug("Last OCI response preview: %s …", last_resp[:400].replace("\n", " "))

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
        self, diff_chunk: str, chunk_idx: int, total_chunks: int, diff_result
    ) -> str:
        rules_text = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(self._rules))
        extra = (
            f"\nAdditional instructions:\n{self.extra_instructions}"
            if self.extra_instructions
            else ""
        )
        return textwrap.dedent(f"""
            You are a senior software engineer performing a code review.
            Focus area: **{self.agent_name}**

            ## Rules to enforce
{rules_text}
{extra}

            ## Context
            - Repository: {diff_result.metadata.repo_url}
            - Source branch (MR): {diff_result.metadata.source_branch}
            - Target branch (prod): {diff_result.metadata.target_branch}
            - Chunk {chunk_idx} of {total_chunks}

            ## Unified Diff (chunk {chunk_idx}/{total_chunks})
            ```diff
            {diff_chunk}
            ```

            ## Required output format
            For every issue found, output exactly this block (repeat for each issue):

            FINDING_START
            SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW|INFO>
            FILE: <file path or "general">
            LINE: <line number or short reference>
            DESCRIPTION: <one-line description of the problem>
            EXPLANATION: <detailed explanation of why this is an issue>
            SUGGESTION: <one-line fix recommendation>
            BEST_PRACTICE: <the best practice rule that was violated>
            FINDING_END

            After all findings output one line:
            SUMMARY: <one sentence summarising the {self.agent_name} health of this diff>

            If no issues are found output ONLY:
            SUMMARY: No {self.agent_name.lower()} issues found.
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
