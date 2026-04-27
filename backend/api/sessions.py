"""
backend/api/sessions.py - Session Management API (Mock Version)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

# Mock Repository 사용 (PostgreSQL 없이 파일 기반)
from backend.repository.mock_repository import (
    MockSessionRepository,
    MockMessageRepository,
    MockDelegationRepository
)

router = APIRouter(tags=["sessions"])

# 전역 Repository 인스턴스
session_repo = MockSessionRepository()
message_repo = MockMessageRepository()
delegation_repo = MockDelegationRepository()


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
@router.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """새 세션 생성"""
    session = session_repo.create(
        user_id=request.user_id,
        chatbot_id=request.chatbot_id,
        session_id=request.session_id
    )
    return SessionResponse(**session)


@router.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    user_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """사용자별 세션 목록 조회 (페이지네이션)"""
    sessions = session_repo.list_by_user(user_id, limit, offset)
    total = session_repo.get_user_session_count(user_id)
    
    return SessionListResponse(
        sessions=[SessionResponse(**s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """세션 상세 조회"""
    session = session_repo.get_by_id(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(**session)


@router.get("/api/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """세션별 메시지 조회 (페이지네이션)"""
    # 세션 존재 확인
    session = session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 메시지 조회
    messages = message_repo.get_by_session(session_id, limit, offset)
    total = message_repo.get_message_count(session_id)
    
    return MessageListResponse(
        messages=[MessageResponse(**m) for m in messages],
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """세션 삭제 (관련 메시지, 위임 체인도 함께 삭제)"""
    import os
    from pathlib import Path
    
    session = session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # 세션 데이터 로드
    from backend.repository.mock_repository import _load_sessions, _save_sessions, DATA_DIR
    
    sessions = _load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        _save_sessions(sessions)
    
    # 메시지 파일 삭제
    msg_file = DATA_DIR / "messages" / f"{session_id}.json"
    if msg_file.exists():
        msg_file.unlink()
    
    return {"status": "success", "message": f"Session {session_id} deleted"}


@router.post("/api/admin/cleanup-sessions")
async def cleanup_old_sessions(days: int = Query(default=30, ge=1)):
    """오래된 세션 정리 (관리자용)"""
    deleted_count = session_repo.delete_old_sessions(days)
    
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "older_than_days": days
    }
