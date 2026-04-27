"""
ADK Web UI Test Agent - Multi Custom Agent Service
"""

import os
from google.adk.agents import Agent
from google.adk.models import OpenAIModel

# 환경에 따른 모델 설정
# DEVELOPMENT=true (Mac 개발환경): Ollama 사용
# DEVELOPMENT=false 또는 미설정 (사내): 사내 LLM Gateway 사용
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    # 개발환경: Ollama (Kimi-k2.5 등 로컬 모델)
    model = OpenAIModel(
        model=os.getenv("OLLAMA_MODEL", "kimi-k2.5"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내환경: 사내 LLM Gateway (OpenAI compatible)
    model = OpenAIModel(
        model=os.getenv("LLM_MODEL", "GLM4.7"),
        base_url=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "")
    )

root_agent = Agent(
    name="chatbot_company_adk",
    model=model,
    instruction="""
    당신은 회사 전체 업무 지원 Root 어시스턴트입니다.
    모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.
    
    답변은 한국어로 작성하세요.
    """,
    description="회사 전체 업무 지원 Root 챗봇 (ADK Web 테스트용)",
)
