# coding: utf-8
"""agents/logic_agent.py"""
from .base_agent import BaseReviewAgent


class LogicAgent(BaseReviewAgent):
    """Reviews code for logic errors, missing error handling, edge-cases."""
    category_key = "logic"
    agent_name = "Logic & Correctness"
    extra_instructions = (
        "Look for potential runtime errors, incorrect conditions, swallowed exceptions, "
        "race conditions, and missing null/edge-case guards."
    )
