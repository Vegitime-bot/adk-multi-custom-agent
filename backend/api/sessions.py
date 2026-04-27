"""
backend/api/sessions.py - Session Management API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.database.session import get_db_session
from backend.repository import (
    PostgreSQLSessionRepository,
    PostgreSQLMessageRepository
)

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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int


# ── API 엔드포인트 ────────────────────────────────────────────────
@router.post("/api/sessions", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    db: DBSession = Depends(get_db_session)
):
    """새 세션 생성"""
    repo = PostgreSQLSessionRepository(db)
    session = repo.create(
        user_id=request.user_id,
        chatbot_id=request.chatbot_id,
        session_id=request.session_id
    )
    return SessionResponse(
        session_id=str(session.session_id),
        user_id=session.user_id,
        chatbot_id=session.chatbot_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_accessed=session.last_accessed.isoformat(),
        message_count=session.message_count
    )


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db_session)
):
    """사용자별 세션 목록 조회 (페이지네이션)"""
    repo = PostgreSQLSessionRepository(db)
    sessions = repo.list_by_user(user_id, limit, offset)
    total = repo.get_user_session_count(user_id)
    
    return SessionListResponse(
        sessions=[
            SessionResponse(
                session_id=str(s.session_id),
                user_id=s.user_id,
                chatbot_id=s.chatbot_id,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                last_accessed=s.last_accessed.isoformat(),
                message_count=s.message_count
            ) for s in sessions
        ],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: DBSession = Depends(get_db_session)
):
    """세션 상세 조회"""
    repo = PostgreSQLSessionRepository(db)
    session = repo.get_by_id(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # last_accessed 업데이트
    repo.update_last_accessed(session_id)
    
    return SessionResponse(
        session_id=str(session.session_id),
        user_id=session.user_id,
        chatbot_id=session.chatbot_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_accessed=session.last_accessed.isoformat(),
        message_count=session.message_count
    )


@router.get("/api/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db_session)
):
    """세션별 메시지 조회 (페이지네이션)"""
    # 세션 존재 확인
    session_repo = PostgreSQLSessionRepository(db)
    session = session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 메시지 조회
    message_repo = PostgreSQLMessageRepository(db)
    messages = message_repo.get_by_session(session_id, limit, offset)
    total = message_repo.get_message_count(session_id)
    
    return MessageListResponse(
        messages=[
            MessageResponse(
                message_id=m.message_id,
                role=m.role,
                content=m.content,
                tokens_used=m.tokens_used,
                latency_ms=m.latency_ms,
                confidence_score=m.confidence_score,
                delegated_to=m.delegated_to,
                created_at=m.created_at.isoformat()
            ) for m in messages
        ],
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: DBSession = Depends(get_db_session)
):
    """세션 삭제 (관련 메시지, 위임 체인도 함께 삭제)"""
    from backend.models.chat_session import ChatSession
    from uuid import UUID
    
    session = db.query(ChatSession).filter(
        ChatSession.session_id == UUID(session_id)
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.delete(session)
    db.commit()
    
    return {"status": "success", "message": f"Session {session_id} deleted"}


@router.post("/api/admin/cleanup-sessions")
async def cleanup_old_sessions(
    days: int = Query(default=30, ge=1),
    db: DBSession = Depends(get_db_session)
):
    """오래된 세션 정리 (관리자용)"""
    repo = PostgreSQLSessionRepository(db)
    deleted_count = repo.delete_old_sessions(days)
    
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "older_than_days": days
    }
