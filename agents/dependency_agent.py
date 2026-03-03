# coding: utf-8
"""agents/dependency_agent.py"""
from .base_agent import BaseReviewAgent


class DependencyAgent(BaseReviewAgent):
    """Reviews changes to dependency files for risks and version issues."""
    category_key = "dependency"
    agent_name = "Dependencies"
    extra_instructions = (
        "Only report issues if the diff touches requirements.txt, pyproject.toml, "
        "setup.py, package.json, or similar dependency manifests. "
        "If no dependency files are changed, output only: "
        "SUMMARY: No dependency file changes detected."
    )
