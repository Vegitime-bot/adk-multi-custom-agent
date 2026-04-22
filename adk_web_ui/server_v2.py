"""
ADK Web UI Server - Phase 2
Knox ID 기반 + 관리자 기능
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 내부 모듈
from config import settings, is_admin, validate_settings
from database import (
    get_or_create_user, update_user_last_active, is_admin as check_is_admin,
    create_session, get_session, get_sessions_by_knox, get_all_sessions,
    reset_session, delete_session, save_message, get_messages, search_messages,
    save_delegation_chain, get_delegation_chain, get_admin_stats, get_user_stats
)
from models import (
    ChatRequest, ChatResponse, SessionCreate, SessionReset,
    AgentInfo, AgentListResponse, AdminStats, UserStats
)

# Agent imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(
    title="ADK Web UI Server - Phase 2",
    version="2.0.0",
    description="Knox ID 기반 채팅 API + 관리자 기능"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Agent Configuration
# ============================================

AGENT_CONFIGS = {
    "chatbot_company_adk": {
        "agent": company_agent,
        "app_name": "chatbot_company_adk",
        "display_name": "회사 전체 지원",
        "description": "모든 사내 문의 처리",
        "level": 0,
        "sub_agents": ["chatbot_hr_adk", "chatbot_tech_adk"]
    },
    "chatbot_hr_adk": {
        "agent": hr_agent,
        "app_name": "chatbot_hr_adk",
        "display_name": "인사지원",
        "description": "인사 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": []
    },
    "chatbot_tech_adk": {
        "agent": tech_agent,
        "app_name": "chatbot_tech_adk",
        "display_name": "기술지원",
        "description": "기술 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": []
    },
}

KEYWORD_DELEGATION = {
    "chatbot_company_adk": {
        "인사": "chatbot_hr_adk",
        "휴가": "chatbot_hr_adk",
        "급여": "chatbot_hr_adk",
        "복지": "chatbot_hr_adk",
        "기술": "chatbot_tech_adk",
        "개발": "chatbot_tech_adk",
        "시스템": "chatbot_tech_adk",
        "버그": "chatbot_tech_adk",
    }
}

# ============================================
# Utility Functions
# ============================================

def get_knox_id(x_knox_id: Optional[str] = Header(None)) -> str:
    """Knox ID 추출 (Header에서)"""
    if not x_knox_id:
        if settings.REQUIRE_KNOX_ID:
            raise HTTPException(status_code=401, detail="X-Knox-Id header required")
        return settings.DEFAULT_KNOX_ID
    return x_knox_id


def check_delegation(current_agent: str, message: str) -> tuple:
    """메시지 내용에 따라 위임 대상 결정"""
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    for keyword, target in keywords.items():
        if keyword in message:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"


def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    """Mock 응답 생성"""
    config = AGENT_CONFIGS[agent_id]
    agent_name = config["display_name"]
    
    response = f"""[{agent_name}] 응답 (Phase 2)

📨 수신 메시지: "{message}"

🔍 Agent 정보:
  - ID: {agent_id}
  - 이름: {agent_name}
  - 레벨: {config['level']}
  - 하위 Agent: {', '.join(config['sub_agents']) if config['sub_agents'] else '없음'}

🔗 위임 체인: {' → '.join(delegation_chain)}

📝 처리 결과: Knox ID 기반 저장 완료
"""
    return response


def verify_session_access(session_id: str, knox_id: str) -> bool:
    """세션 접근 권한 확인"""
    session = get_session(session_id)
    if not session:
        return False
    # 본인이거나 관리자면 접근 가능
    if session['knox_id'] == knox_id:
        return True
    return check_is_admin(knox_id)


# ============================================
# Public API (Knox ID 기반)
# ============================================

@app.get("/")
async def root():
    """메인 페이지"""
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / "index_db.html")


@app.get("/api/agents/detail")
async def get_agents_detail() -> AgentListResponse:
    """상세 Agent 정보"""
    agents = [
        AgentInfo(
            id=agent_id,
            name=config["display_name"],
            description=config["description"],
            level=config["level"],
            app_name=config["app_name"],
            sub_agents=config.get("sub_agents", []),
            parent=config.get("parent")
        )
        for agent_id, config in AGENT_CONFIGS.items()
    ]
    return AgentListResponse(agents=agents)


@app.post("/api/run")
async def run_agent(request: ChatRequest, x_knox_id: Optional[str] = Header(None)):
    """Agent 실행 + DB 저장 (Knox ID 필수)"""
    
    # Knox ID 확인
    knox_id = x_knox_id or settings.DEFAULT_KNOX_ID
    if settings.REQUIRE_KNOX_ID and not x_knox_id:
        raise HTTPException(status_code=401, detail="X-Knox-Id header required")
    
    # Agent 검증
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    
    # 사용자 확인/생성
    get_or_create_user(knox_id)
    update_user_last_active(knox_id)
    
    # 세션 생성 (Knox ID 포함)
    create_session(request.session_id, knox_id, request.agent)
    
    # 위임 체크
    delegated_agent, reason = check_delegation(request.agent, request.message)
    
    # 위임 체인 생성
    chain = [request.agent]
    if delegated_agent != request.agent:
        chain.append(delegated_agent)
    
    # 위임 체인 저장
    save_delegation_chain(request.session_id, chain)
    
    # 메시지 저장
    save_message(request.session_id, "user", request.message, request.agent)
    
    # Mock 응답 생성
    response_text = generate_mock_response(delegated_agent, request.message, chain)
    
    # 어시스턴트 응답 저장
    save_message(request.session_id, "assistant", response_text, delegated_agent)
    
    return ChatResponse(
        response=response_text,
        session_id=request.session_id,
        agent_used=delegated_agent,
        delegation_chain=chain,
        debug_info={
            "original_agent": request.agent,
            "delegated_agent": delegated_agent,
            "delegation_reason": reason,
            "knox_id": knox_id,
            "is_admin": check_is_admin(knox_id)
        }
    )


@app.get("/api/sessions")
async def list_sessions(x_knox_id: Optional[str] = Header(None)):
    """세션 목록 - 본인 것만 반환 (관리자는 전체)"""
    knox_id = x_knox_id or settings.DEFAULT_KNOX_ID
    
    # 관리자면 전체 반환
    if check_is_admin(knox_id):
        sessions = get_all_sessions()
    else:
        sessions = get_sessions_by_knox(knox_id)
    
    # 각 세션에 위임 체인 추가
    result = []
    for session in sessions:
        chain = get_delegation_chain(session['session_id'])
        session['delegation_chain'] = chain
        result.append(session)
    
    return {"sessions": result}


@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str, x_knox_id: Optional[str] = Header(None)):
    """세션 히스토리 - 권한 체크"""
    knox_id = x_knox_id or settings.DEFAULT_KNOX_ID
    
    # 권한 확인
    if not verify_session_access(session_id, knox_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    history = get_messages(session_id)
    chain = get_delegation_chain(session_id)
    
    return {
        "session_id": session_id,
        "history": history,
        "delegation_chain": chain,
        "knox_id": knox_id
    }


@app.post("/api/session/reset")
async def reset_session_endpoint(request: SessionReset, x_knox_id: Optional[str] = Header(None)):
    """세션 초기화 - 권한 체크"""
    knox_id = x_knox_id or settings.DEFAULT_KNOX_ID
    
    # 권한 확인
    if not verify_session_access(request.session_id, knox_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = reset_session(request.session_id)
    
    return {
        "status": "success" if success else "error",
        "message": f"Session '{request.session_id}' has been reset",
        "session_id": request.session_id
    }


@app.delete("/api/session/{session_id}")
async def delete_session_endpoint(session_id: str, x_knox_id: Optional[str] = Header(None)):
    """세션 삭제 - 권한 체크"""
    knox_id = x_knox_id or settings.DEFAULT_KNOX_ID
    
    # 권한 확인
    if not verify_session_access(session_id, knox_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = delete_session(session_id)
    
    return {
        "status": "success" if success else "error",
        "message": f"Session '{session_id}' deleted"
    }


# ============================================
# Admin API
# ============================================

def require_admin_header(x_knox_id: Optional[str] = Header(None)):
    """관리자 권한 요구"""
    knox_id = x_knox_id or ""
    if not check_is_admin(knox_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return knox_id


@app.get("/api/admin/stats")
async def admin_stats(admin_knox_id: str = Depends(require_admin_header)):
    """관리자 통계"""
    stats = get_admin_stats()
    return {
        "stats": stats,
        "requested_by": admin_knox_id
    }


@app.get("/api/admin/users")
async def admin_users(admin_knox_id: str = Depends(require_admin_header)):
    """사용자 목록"""
    users = get_user_stats()
    return {
        "users": users,
        "requested_by": admin_knox_id
    }


@app.get("/api/admin/sessions")
async def admin_sessions(
    knox_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 100,
    admin_knox_id: str = Depends(require_admin_header)
):
    """전체 세션 목록 (관리자용)"""
    sessions = get_all_sessions(knox_id, is_active, limit)
    return {
        "sessions": sessions,
        "requested_by": admin_knox_id
    }


@app.get("/api/admin/user/{user_knox_id}/sessions")
async def admin_user_sessions(
    user_knox_id: str,
    admin_knox_id: str = Depends(require_admin_header)
):
    """특정 사용자의 세션"""
    sessions = get_sessions_by_knox(user_knox_id)
    return {
        "knox_id": user_knox_id,
        "sessions": sessions,
        "requested_by": admin_knox_id
    }


@app.post("/api/admin/user/{user_knox_id}/admin")
async def set_user_admin(
    user_knox_id: str,
    is_admin_flag: bool = True,
    admin_knox_id: str = Depends(require_admin_header)
):
    """사용자 관리자 권한 설정"""
    from database import set_admin
    set_admin(user_knox_id, is_admin_flag)
    return {
        "status": "success",
        "knox_id": user_knox_id,
        "is_admin": is_admin_flag,
        "set_by": admin_knox_id
    }


# ============================================
# Static Files
# ============================================

app.mount("/static", StaticFiles(directory=Path(__file__).parent), name="static")


# ============================================
# Startup
# ============================================

@app.on_event("startup")
async def startup_event():
    """시작 시 설정 검증"""
    warnings = validate_settings()
    for warning in warnings:
        print(warning)
    
    print("=" * 70)
    print("ADK Web UI Server - Phase 2 (Knox ID + Admin)")
    print("=" * 70)
    print(f"\nDatabase: {'SQLite' if settings.USE_SQLITE else 'PostgreSQL'}")
    print(f"Admin Knox IDs: {settings.ADMIN_KNOX_LIST}")
    print(f"Require Knox ID: {settings.REQUIRE_KNOX_ID}")
    print("\n엔드포인트:")
    print("  GET  /api/agents/detail")
    print("  POST /api/run              - 채팅 (X-Knox-Id 헤더 필수)")
    print("  GET  /api/sessions         - 본인 세션만")
    print("  GET  /api/session/{id}/history")
    print("  POST /api/session/reset")
    print("  DELETE /api/session/{id}")
    print("\n관리자 API:")
    print("  GET  /api/admin/stats      - 전체 통계")
    print("  GET  /api/admin/users      - 사용자 목록")
    print("  GET  /api/admin/sessions   - 전체 세션")
    print("\n접속: http://localhost:8093")
    print("=" * 70)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8093, log_level="info")
