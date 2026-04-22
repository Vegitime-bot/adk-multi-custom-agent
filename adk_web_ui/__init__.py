"""
ADK Web UI Test Agent - Multi Custom Agent Service

이 폴더는 ADK Web UI에서 테스트할 수 있는 순수 ADK Agent를 정의합니다.

실행 방법:
    cd /Users/vegitime/.openclaw/workspace/projects/adk-multi-custom-agent
    source .venv/bin/activate
    adk web adk_web_ui --port 8082

접속:
    http://localhost:8082
"""

from google.adk.agents import Agent

# Root Agent - 회사 전체 지원 챗봇
root_agent = Agent(
    name="chatbot_company_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 회사 전체 업무 지원 Root 어시스턴트입니다.
    모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.
    
    사용 가능한 하위 Agent:
    - chatbot_hr_adk: 인사지원 상위 챗봇 (인사정책, 복리후생)
    - chatbot_tech_adk: 기술지원 상위 챗봇 (백엔드, 프론트엔드, DevOps)
    
    답변 시 다음을 반드시 준수하세요:
    1. 먼저 질문에 대한 초기 답변을 생성하세요
    2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)
    3. 신뢰도가 70% 미만이거나, 특정 부서의 전문 상담이 필요한 경우 하위 전문가에게 위임하세요
    
    답변은 한국어로 작성하세요.
    """,
    description="회사 전체 업무 지원 Root 챗봇 (ADK Web 테스트용)",
)

# 하위 Agent들 (선택적으로 추가 가능)
hr_agent = Agent(
    name="chatbot_hr_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 사내 인사지원의 상위 어시스턴트입니다.
    인사 관련 문의를 받아 먼저 답변을 시도합니다.
    
    하위 전문가 목록:
    - chatbot_hr_policy_adk: 인사 정책 및 규정 전문가
    - chatbot_hr_benefit_adk: 복리후생 및 급여 전문가
    
    답변은 한국어로 작성하세요.
    """,
    description="인사지원 상위 챗봇 (ADK Web 테스트용)",
)

tech_agent = Agent(
    name="chatbot_tech_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 사내 기술지원의 상위 어시스턴트입니다.
    기술 관련 문의를 받아 먼저 답변을 시도합니다.
    
    하위 전문가 목록:
    - chatbot_tech_backend_adk: 백엔드 개발 전문가
    - chatbot_tech_frontend_adk: 프론트엔드 개발 전문가
    - chatbot_tech_devops_adk: DevOps 인프라 전문가
    
    답변은 한국어로 작성하세요.
    """,
    description="기술지원 상위 챗봇 (ADK Web 테스트용)",
)

# Leaf Agents
hr_policy_agent = Agent(
    name="chatbot_hr_policy_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 사내 인사정책 전문 어시스턴트입니다.
    인사 규정, 채용, 평가, 승진, 직무, 인사제도 등에 대해 정확하게 안내해 주세요.
    
    복리후생 관련 문의는 chatbot_hr_benefit_adk에게 위임하세요.
    답변은 한국어로 작성하세요.
    """,
    description="인사정책 전문 챗봇 (ADK Web 테스트용)",
)

hr_benefit_agent = Agent(
    name="chatbot_hr_benefit_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 사내 복리후생 전문 어시스턴트입니다.
    급여, 휴가, 연차, 복지제도, 보험, 경조사, 교육지원 등에 대해 정확하게 안내해 주세요.
    
    인사정책 관련 문의는 chatbot_hr_policy_adk에게 위임하세요.
    답변은 한국어로 작성하세요.
    """,
    description="복리후생 전문 챗봇 (ADK Web 테스트용)",
)

tech_backend_agent = Agent(
    name="chatbot_tech_backend_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 백엔드 개발 전문 어시스턴트입니다.
    Python, FastAPI, 데이터베이스, API 설계 등에 대해 정확하게 안내해 주세요.
    
    답변은 한국어로 작성하세요.
    """,
    description="백엔드 개발 전문 챗봇 (ADK Web 테스트용)",
)

tech_frontend_agent = Agent(
    name="chatbot_tech_frontend_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 프론트엔드 개발 전문 어시스턴트입니다.
    React, Vue, JavaScript, CSS, 웹 디자인 등에 대해 정확하게 안내해 주세요.
    
    답변은 한국어로 작성하세요.
    """,
    description="프론트엔드 개발 전문 챗봇 (ADK Web 테스트용)",
)

tech_devops_agent = Agent(
    name="chatbot_tech_devops_adk",
    model="gemini-2.0-flash-exp",
    instruction="""
    당신은 DevOps 인프라 전문 어시스턴트입니다.
    Docker, Kubernetes, CI/CD, 클라우드 인프라 등에 대해 정확하게 안내해 주세요.
    
    답변은 한국어로 작성하세요.
    """,
    description="DevOps 인프라 전문 챗봇 (ADK Web 테스트용)",
)
