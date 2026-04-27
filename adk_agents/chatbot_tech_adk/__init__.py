"""
Tech Agent for ADK Web UI
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 명시적 로드
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

# 환경에 따른 모델 설정
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    # 개발환경: Ollama
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내환경
    model = LiteLlm(
        model=f"openai/{os.getenv('LLM_MODEL', 'GLM4.7')}",
        api_base=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "")
    )

root_agent = Agent(
    name="chatbot_tech_adk",
    model=model,
    instruction="""
    당신은 사내 기술지원의 상위 어시스턴트입니다.
    기술 관련 문의를 받아 먼저 답변을 시도합니다.
    답변은 한국어로 작성하세요.
    """,
    description="기술지원 상위 챗봇 (ADK Web 테스트용)",
)
