"""
Architecture Agent - 시스템 설계 및 아키텍처 담당
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
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    model = LiteLlm(
        model=f"openai/{os.getenv('LLM_DEFAULT_MODEL', 'GLM4.7')}",
        api_base=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "")
    )

agent = Agent(
    name="architecture_agent",
    model=model,
    instruction="""
    당신은 소프트웨어 아키텍처 설계 전문가입니다.
    
    역할:
    1. 시스템 구조 설계 및 컴포넌트 정의
    2. 데이터 흐름 및 API 설계
    3. 기술 스택 선정 및 이유 제시
    4. 확장성 및 성능 고려사항 분석
    5. 리스크 및 대안 제시
    
    출력 형식:
    - 설계 문서 (Markdown)
    - 다이어그램 설명 (Mermaid 또는 텍스트)
    - 결정 사항 및 근거
    
    모든 분석은 한국어로 제공하세요.
    """,
    description="시스템 아키텍처 설계 전문가 Agent",
)
