# coding: utf-8
"""
reviewer.py
Orchestrates all review agents concurrently and aggregates results.
Supports OCI Generative AI and Anthropic Claude as AI backends.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List

from git_client import DiffResult
from oci_client import OCIGenAIClient
from claude_client import ClaudeClient
from config import AI_PROVIDER, runtime_config
from agents import (
    SecurityAgent,
    StyleAgent,
    LogicAgent,
    PerformanceAgent,
    DependencyAgent,
)
from agents.base_agent import AgentResult
from logger import get_logger

log = get_logger(__name__)


@dataclass
class ReviewReport:
    """Aggregated report from all agents."""
    diff_result: DiffResult
    agent_results: List[AgentResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def total_findings(self) -> int:
        return sum(len(r.findings) for r in self.agent_results)

    @property
    def severity_totals(self) -> dict:
        totals = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        for result in self.agent_results:
            for sev, count in result.severity_counts.items():
                totals[sev] = totals.get(sev, 0) + count
        return totals

    @property
    def overall_status(self) -> str:
        """Quick pass/fail judgement based on critical and high findings."""
        totals = self.severity_totals
        if totals["CRITICAL"] > 0:
            return "BLOCKED"           # Must fix before merge
        if totals["HIGH"] > 0:
            return "NEEDS WORK"        # Should fix before merge
        if totals["MEDIUM"] > 0:
            return "REVIEW REQUIRED"   # Discuss before merge
        return "APPROVED"              # No blocking issues


class CodeReviewer:
    """
    Runs all five review agents against a DiffResult and returns a ReviewReport.
    Agents run concurrently to minimise wall-clock time.

    The AI provider (OCI or Claude) is resolved from runtime_config at review
    time so that it can be switched in the Settings page without a server restart.
    """

    def __init__(self):
        # Resolve provider from runtime config first, fall back to .env / config.py default
        provider = (runtime_config.get("ai_provider") or AI_PROVIDER).lower()
        log.info("Initialising CodeReviewer | provider=%s …", provider)

        if provider == "claude":
            self._ai_client = ClaudeClient()
        else:
            self._ai_client = OCIGenAIClient()

        # All available agent classes keyed by their category_key
        self._all_agent_classes = {
            "security":    SecurityAgent,
            "style":       StyleAgent,
            "logic":       LogicAgent,
            "performance": PerformanceAgent,
            "dependency":  DependencyAgent,
        }

    def review(self, diff_result: DiffResult, enabled_agents: List[str] = None) -> ReviewReport:
        """
        Run enabled agents against the diff and return an aggregated ReviewReport.

        Args:
            diff_result:    Output from :class:`OracleVBSGitClient.get_diff`.
            enabled_agents: List of category keys to run (e.g. ["security", "logic"]).
                            Defaults to all five agents when None or empty.

        Returns:
            :class:`ReviewReport` with all agent findings.
        """
        # Resolve which agent classes to run
        if enabled_agents:
            agent_classes = [
                cls for key, cls in self._all_agent_classes.items()
                if key in enabled_agents
            ]
        else:
            agent_classes = list(self._all_agent_classes.values())

        if not agent_classes:
            # Shouldn't happen due to api.py guard, but be safe
            agent_classes = list(self._all_agent_classes.values())

        start = time.monotonic()
        agent_instances = [cls(self._ai_client) for cls in agent_classes]
        results: List[AgentResult] = []

        log.info("Launching %d agent(s) in parallel: %s …",
                 len(agent_instances),
                 ", ".join(a.agent_name for a in agent_instances))

        with ThreadPoolExecutor(max_workers=len(agent_instances)) as executor:
            future_to_agent = {
                executor.submit(agent.review, diff_result): agent.agent_name
                for agent in agent_instances
            }
            for future in as_completed(future_to_agent):
                agent_name = future_to_agent[future]
                try:
                    result = future.result()
                    results.append(result)
                    finding_count = len(result.findings)
                    error_tag = " | ⚠ OCI errors occurred" if result.had_errors else ""

                    log.info(
                        "Agent '%s' finished → %d finding(s)%s",
                        agent_name, finding_count, error_tag,
                    )

                    # At INFO level show what OCI said when 0 findings (confirms it ran)
                    if finding_count == 0 and not result.had_errors and result.raw_responses:
                        last = result.raw_responses[-1]
                        snippet = last[:300].replace("\n", " ")
                        log.info(
                            "Agent '%s' OCI response preview: %s …",
                            agent_name, snippet,
                        )

                except Exception as exc:
                    log.error(
                        "Agent '%s' raised an unhandled exception.\n"
                        "  WHAT WENT WRONG : %s\n"
                        "  WHAT TO DO      : Check the log file in logs/ for the full "
                        "stack trace. This is likely a bug in the agent code, not an OCI issue.",
                        agent_name, exc,
                        exc_info=True,
                    )
                    results.append(AgentResult(
                        agent_name=agent_name,
                        summary=f"Agent crashed: {exc}",
                        had_errors=True,
                    ))

        elapsed = time.monotonic() - start
        report = ReviewReport(
            diff_result=diff_result,
            agent_results=results,
            elapsed_seconds=round(elapsed, 2),
        )

        log.info(
            "All agents complete → overall status: %s | total findings: %d | "
            "elapsed: %.2fs",
            report.overall_status, report.total_findings, elapsed,
        )
        log.debug("Severity breakdown: %s", report.severity_totals)

        return report
