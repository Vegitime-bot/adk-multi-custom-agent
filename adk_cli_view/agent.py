"""
ADK CLI Web Console용 Root Agent

이 파일은 adk web 명령어로 실행됩니다:
    adk web adk_cli_view --port 8000

현재 시스템의 ADK Agents를 로드하여 보여줍니다.
"""
import os
import sys

# 프로젝트 루트 추가
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from adk_agents.delegation_router_agent import get_router

# ADK CLI가 찾는 root_agent
router = get_router()
root_agent = router.root_agent
