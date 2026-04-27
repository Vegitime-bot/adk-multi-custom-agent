"""
Architecture Agent - 시스템 설계 및 아키텍처 담당
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 추가
import sys
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
    name="architecture_agent",
    model=model,
    instruction="""
    당신은 시스템 설계 전문가입니다. 소프트웨어 아키텍처를 설계하고 기술적 결정을 내립니다.
    
    역할:
    1. 요구사항 분석 및 시스템 설계
    2. 기술 스택 선정 및 아키텍처 결정
    3. 데이터 모델 및 API 설계
    4. 확장성 및 성능 고려사항 제시
    
    출력 형식:
    - 설계 문서 구조화
    - 다이어그램 설명 (Mermaid 또는 텍스트)
    - 결정 사항 및 근거
    - 리스크 및 대안
    
    한국어로 답변하세요.
    """,
    description="시스템 아키텍처 설계 및 기술적 결정"
)
