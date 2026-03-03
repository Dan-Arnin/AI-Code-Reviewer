# coding: utf-8
"""agents/style_agent.py"""
from .base_agent import BaseReviewAgent


class StyleAgent(BaseReviewAgent):
    """Reviews code for PEP-8, naming, docstrings and readability."""
    category_key = "style"
    agent_name = "Code Style"
    extra_instructions = (
        "Evaluate readability and maintainability. Flag dead code, missing type hints, "
        "unclear variable names, and missing docstrings on public APIs."
    )
