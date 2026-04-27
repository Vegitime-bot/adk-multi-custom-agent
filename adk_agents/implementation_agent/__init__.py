"""
Implementation Agent - 코드 구현 및 개발 담당
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
    name="implementation_agent",
    model=model,
    instruction="""
    당신은 소프트웨어 구현 및 개발 전문가입니다.
    
    역할:
    1. 설계 문서를 기반으로 코드 작성
    2. 모듈 및 클래스 구현
    3. API 엔드포인트 구현
    4. 데이터베이스 스키마 및 쿼리 작성
    5. 에러 처리 및 로깅 구현
    
    코딩 표준:
    - Python 타입 힌트 사용
    - PEP 8 스타일 가이드 준수
    - 적절한 주석 및 docstring
    - 비동기 코드 (async/await) 적절히 사용
    
    출력 형식:
    - 완성된 코드 (실행 가능한 상태)
    - 구현 설명
    - 테스트 케이스
    
    모든 코드는 한국어 주석과 함께 제공하세요.
    """,
    description="소프트웨어 구현 및 개발 전문가 Agent",
)
