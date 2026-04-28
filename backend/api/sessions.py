"""
backend/api/sessions.py - ADK 기반 세션 관리 API

ADK InMemorySessionService를 사용하여 세션을 관리합니다.
기존 MockRepository 기반에서 ADK로 완전히 대체됩니다.
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel

from backend.adk.adk_session_wrapper import get_session_wrapper

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])


# ── 스키마 ───────────────────────────────────────────────────────
class SessionCreateRequest(BaseModel):
    user_id: str
    chatbot_id: str
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    chatbot_id: str
    created_at: str
    updated_at: str
    last_accessed: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    message_id: int
    role: str
    content: str
    tokens_used: int
    latency_ms: int
    confidence_score: Optional[float]
    delegated_to: Optional[str]
    created_at: str


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int


# ── API 엔드포인트 ────────────────────────────────────────────────
@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """새 ADK 세션 생성"""
    wrapper = get_session_wrapper()
    
    # ADK 세션 생성
    session = wrapper.get_or_create(
        chatbot_id=request.chatbot_id,
        user_knox_id=request.user_id,
        session_id=request.session_id
    )
    
    now = datetime.utcnow().isoformat()
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_knox_id,
        chatbot_id=session.chatbot_id,
        created_at=now,
        updated_at=now,
        last_accessed=now,
        message_count=0
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """ADK 사용자별 세션 목록 조회"""
    wrapper = get_session_wrapper()
    
    # ADK에서 세션 목록 조회
    all_sessions = wrapper.list_sessions(user_knox_id=user_id)
    
    # 페이징 처리
    total = len(all_sessions)
    paginated = all_sessions[offset:offset + limit]
    
    sessions = []
    for s in paginated:
        sessions.append(SessionResponse(
            session_id=s.get("session_id", ""),
            user_id=s.get("user_knox_id", user_id),
            chatbot_id=s.get("chatbot_id", ""),
            created_at=s.get("created_at", ""),
            updated_at=datetime.utcnow().isoformat(),
            last_accessed=datetime.utcnow().isoformat(),
            message_count=0  # ADK는 메시지 카운트 별도 관리
        ))
    
    return SessionListResponse(
        sessions=sessions,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """ADK 세션 상세 조회"""
    wrapper = get_session_wrapper()
    
    session = wrapper.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    now = datetime.utcnow().isoformat()
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_knox_id,
        chatbot_id=session.chatbot_id,
        created_at=now,
        updated_at=now,
        last_accessed=now,
        message_count=0
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """ADK 세션 삭제"""
    wrapper = get_session_wrapper()
    
    # 세션 존재 확인
    session = wrapper.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # ADK 세션 종료
    success = wrapper.close_session(session_id)
    
    return {
        "status": "success" if success else "error",
        "message": f"Session {session_id} deleted"
    }


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    ADK 세션 메시지 조회
    
    현재 ADK InMemorySessionService는 이벤트 히스토리를 메모리에 유지합니다.
    영구 저장이 필요하면 conversation_logs 테이블과 연동하세요.
    """
    wrapper = get_session_wrapper()
    
    # 세션 존재 확인
    session = wrapper.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # ADK 세션에서 이벤트 추출 (events 속성이 있는 경우)
    messages = []
    try:
        # 내부 ADK 세션 접근
        adk_sessions = getattr(wrapper._session_service, '_sessions', {})
        for key, adk_session in adk_sessions.items():
            if adk_session.session_id == session_id:
                if hasattr(adk_session, 'events'):
                    for i, event in enumerate(adk_session.events):
                        messages.append({
                            "message_id": i + 1,
                            "role": getattr(event, 'role', 'unknown'),
                            "content": getattr(event, 'content', ''),
                            "tokens_used": 0,
                            "latency_ms": 0,
                            "confidence_score": None,
                            "delegated_to": None,
                            "created_at": getattr(event, 'timestamp', datetime.utcnow().isoformat())
                        })
                break
    except Exception as e:
        logger.warning(f"Failed to get ADK events: {e}")
    
    # 페이징
    total = len(messages)
    paginated = messages[offset:offset + limit]
    
    return {
        "messages": paginated,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/api/admin/cleanup-sessions")
async def cleanup_old_sessions(days: int = Query(default=30, ge=1)):
    """오래된 ADK 세션 정리 (관리자용)"""
    # ADK는 자동으로 메모리를 관리하지만, 필요시 수동 정리
    # 현재 InMemorySessionService는 TTL을 지원하지 않음
    return {
        "status": "info",
        "message": "ADK InMemorySessionService does not support manual cleanup. Sessions persist in memory until server restart."
    }