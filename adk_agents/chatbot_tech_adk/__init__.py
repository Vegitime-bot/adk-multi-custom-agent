"""
Tech Agent for ADK Web UI
"""

from google.adk.agents import Agent
from google.adk.models import OpenAIModel

# Local LLM (Ollama) 설정
local_model = OpenAIModel(
    model="GLM4.7",
    base_url="http://localhost:11434/v1",
    api_key="dummy-key"
)

root_agent = Agent(
    name="chatbot_tech_adk",
    model=local_model,
    instruction="""
    당신은 사내 기술지원의 상위 어시스턴트입니다.
    기술 관련 문의를 받아 먼저 답변을 시도합니다.
    답변은 한국어로 작성하세요.
    """,
    description="기술지원 상위 챗봇 (ADK Web 테스트용)",
)
