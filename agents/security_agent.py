# coding: utf-8
"""agents/security_agent.py"""
from .base_agent import BaseReviewAgent


class SecurityAgent(BaseReviewAgent):
    """Reviews code changes for OWASP / security best-practice violations."""
    category_key = "security"
    agent_name = "Security"
    extra_instructions = (
        "Pay special attention to authentication, authorisation, input validation, "
        "cryptography, secrets management, and dependency vulnerabilities."
    )
