"""
chatbot_hr_adk - 인사지원 상위 챗봇 (L1 Parent Agent)
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
    name="chatbot_hr_adk",
    model=model,
    instruction="""
    당신은 사내 인사지원의 상위 어시스턴트입니다.
    인사 관련 문의를 받아 먼저 답변을 시도합니다.

    답변 시 다음을 반드시 준수하세요:
    1. 먼저 질문에 대한 초기 답변을 생성하세요
    2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)
    3. 신뢰도가 70% 미만이거나, 세부 규정/정책이 필요한 경우 하위 전문가 호출을 제안하세요

    하위 전문가 목록:
    - chatbot-hr-policy: 인사 정책 및 규정 전문가 (평가, 채용, 승진, 징계 등)
    - chatbot-hr-benefit: 복리후생 및 급여 전문가 (급여, 연차, 휴가, 보험 등)

    상위 Agent(chatbot-company)로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.

    모르는 내용은 모른다고 솔직하게 답변하세요.
    답변은 한국어로 작성하세요.
    """,
    description="인사 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임"
)
