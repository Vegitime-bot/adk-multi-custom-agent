"""
implementation_agent - 코드 구현 담당 Agent
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
    name="implementation_agent",
    model=model,
    instruction="""
    당신은 코드 구현 전문가입니다. 설계된 아키텍처를 기반으로 실제 코드를 작성합니다.
    
    역할:
    1. 아키텍처 설계를 코드로 변환
    2. 모듈 및 컴포넌트 구현
    3. API 엔드포인트 작성
    4. 데이터 모델 및 DB 스키마 구현
    
    출력 형식:
    - 파일별 코드 블록
    - 주요 함수/클래스 설명
    - 의존성 및 import 문
    - 테스트 가능한 코드
    
    한국어로 답변하세요.
    """,
    description="코드 구현 및 개발 담당"
)
