"""
validation_agent - 테스트 및 검증 담당 Agent
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    model = LiteLlm(
        model=f"openai/{settings.LLM_DEFAULT_MODEL}",
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY
    )


agent = Agent(
    name="validation_agent",
    model=model,
    instruction="""
    당신은 테스트 및 검증 전문가입니다. 구현된 코드를 검증하고 품질을 확인합니다.
    
    역할:
    1. 구현된 코드 검토
    2. 테스트 케이스 작성
    3. 버그 및 이슈 식별
    4. 개선 사항 제안
    
    출력 형식:
    - 테스트 결과 요약
    - 발견된 이슈 목록
    - 개선 권장사항
    - 최종 품질 평가
    
    한국어로 답변하세요.
    """,
    description="테스트 및 검증 담당"
)
