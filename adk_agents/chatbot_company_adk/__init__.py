"""
ADK Web UI Test Agent - Multi Custom Agent Service
"""

from google.adk.agents import Agent
from google.adk.models import OpenAIModel

# Local LLM (Ollama) 설정
local_model = OpenAIModel(
    model="GLM4.7",  # 또는 사용 중인 모델명
    base_url="http://localhost:11434/v1",
    api_key="dummy-key"  # Ollama는 API key 불필요
)

root_agent = Agent(
    name="chatbot_company_adk",
    model=local_model,
    instruction="""
    당신은 회사 전체 업무 지원 Root 어시스턴트입니다.
    모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.
    
    답변은 한국어로 작성하세요.
    """,
    description="회사 전체 업무 지원 Root 챗봇 (ADK Web 테스트용)",
)
