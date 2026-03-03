# coding: utf-8
"""agents/performance_agent.py"""
from .base_agent import BaseReviewAgent


class PerformanceAgent(BaseReviewAgent):
    """Reviews code for performance anti-patterns and resource leaks."""
    category_key = "performance"
    agent_name = "Performance"
    extra_instructions = (
        "Focus on database query patterns, memory allocation, I/O efficiency, "
        "blocking calls in async contexts, and unnecessary computation."
    )
