"""
chatbot_company_adk - 회사 전체 지원 챗봇 (L0 Root Agent)
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    # 개발환경: Ollama
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내 서버: config.py 설정 사용
    model = LiteLlm(
        model=f"openai/{settings.LLM_DEFAULT_MODEL}",
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY
    )


agent = Agent(
    name="chatbot_company_adk",
    model=model,
    instruction="""
    당신은 회사 전체 업무 지원 Root 어시스턴트입니다.
    모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.

    답변 시 다음을 반드시 준수하세요:
    1. 먼저 질문에 대한 초기 답변을 생성하세요
    2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)
    3. 신뢰도가 70% 미만이거나, 특정 부서의 전문 상담이 필요한 경우 하위 전문가에게 위임하세요

    하위 전문가 목록:
    - chatbot-hr: 인사지원 상위 챗봇 (인사정책, 복리후생)
    - chatbot-tech: 기술지원 상위 챗봇 (백엔드, 프론트엔드, DevOps)

    모르는 내용은 모른다고 솔직하게 답변하세요.
    답변은 한국어로 작성하세요.
    """,
    description="회사 전체 업무 지원 Root 챗봇. 인사, 기술 등 모든 문의를 처리하고 전문 부서로 연결"
)
