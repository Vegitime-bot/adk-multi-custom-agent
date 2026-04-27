"""
HR Agent for ADK Web UI
"""

import os
from google.adk.agents import Agent
from google.adk.models import OpenAIModel

# 환경에 따른 모델 설정
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    # 개발환경: Ollama (Kimi-k2.5 등 로컬 모델)
    model = OpenAIModel(
        model=os.getenv("OLLAMA_MODEL", "kimi-k2.5"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내환경: 사내 LLM Gateway
    model = OpenAIModel(
        model=os.getenv("LLM_MODEL", "GLM4.7"),
        base_url=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "")
    )

root_agent = Agent(
    name="chatbot_hr_adk",
    model=model,
    instruction="""
    당신은 사내 인사지원의 상위 어시스턴트입니다.
    인사 관련 문의를 받아 먼저 답변을 시도합니다.
    답변은 한국어로 작성하세요.
    """,
    description="인사지원 상위 챗봇 (ADK Web 테스트용)",
)
