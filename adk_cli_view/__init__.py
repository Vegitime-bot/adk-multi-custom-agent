"""ADK CLI Web Console용 Agent 패키지

사용법:
    adk web adk_cli_view --host 0.0.0.0 --port 8000
"""
from .agent import root_agent

__all__ = ["root_agent"]