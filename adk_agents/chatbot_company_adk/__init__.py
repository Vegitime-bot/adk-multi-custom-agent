"""
ADK Web UI Test Agent - Multi Custom Agent Service
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 명시적 로드 (adk_agents 폴더 기준 상위 경로)
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

# 환경에 따른 모델 설정
# DEVELOPMENT=true (Mac 개발환경): Ollama 사용
# DEVELOPMENT=false 또는 미설정 (사내): 사내 LLM Gateway 사용
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

# 디버그: 실제로 읽은 환경변수 출력 (문제 해결 후 제거)
print(f"[DEBUG chatbot_company_adk] DEVELOPMENT={os.getenv('DEVELOPMENT')}")
print(f"[DEBUG chatbot_company_adk] LLM_DEFAULT_MODEL={os.getenv('LLM_DEFAULT_MODEL')}")
print(f"[DEBUG chatbot_company_adk] LLM_BASE_URL={os.getenv('LLM_BASE_URL')}")

if IS_DEVELOPMENT:
    # 개발환경: Ollama (Kimi-k2.5 등 로컬 모델)
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내환경: 사내 LLM Gateway (OpenAI compatible)
    # .env.example과 동일한 변수명 사용
    model_name = os.getenv("LLM_DEFAULT_MODEL", "GLM4.7")
    api_base = os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1")
    api_key = os.getenv("LLM_API_KEY", "")
    
    print(f"[DEBUG chatbot_company_adk] Using corporate model: {model_name}")
    print(f"[DEBUG chatbot_company_adk] API base: {api_base}")
    
    model = LiteLlm(
        model=f"openai/{model_name}",
        api_base=api_base,
        api_key=api_key
    )

agent = Agent(
    name="chatbot_company_adk",
    model=model,
    instruction="""
    당신은 회사 전체 업무 지원 Root 어시스턴트입니다.
    모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.
    
    답변은 한국어로 작성하세요.
    """,
    description="회사 전체 업무 지원 Root 챗봇 (ADK Web 테스트용)",
)
