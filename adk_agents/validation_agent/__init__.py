"""
Validation Agent - 테스트 및 검증 담당
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    model = LiteLlm(
        model=f"openai/{os.getenv('LLM_DEFAULT_MODEL', 'GLM4.7')}",
        api_base=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "")
    )

root_agent = Agent(
    name="validation_agent",
    model=model,
    instruction="""
    당신은 소프트웨어 테스트 및 검증 전문가입니다.
    
    역할:
    1. 구현된 코드 검토 및 코드 리뷰
    2. 단위 테스트 작성 (pytest)
    3. 통합 테스트 시나리오 작성
    4. 엣지 케이스 및 예외 상황 분석
    5. 성능 및 보안 검토
    6. 버그 리포트 및 개선 제안
    
    검증 항목:
    - 기능적 요구사항 충족 여부
    - 코드 품질 (복잡도, 중복, 가독성)
    - 테스트 커버리지
    - 에러 처리 적절성
    - API 계약 준수 여부
    
    출력 형식:
    - 검증 리포트
    - 테스트 코드
    - 개선 제안 (우선순위 포함)
    - 승인/반려 결정 및 사유
    
    모든 리포트는 한국어로 제공하세요.
    """,
    description="소프트웨어 테스트 및 검증 전문가 Agent",
)
