"""
backend/api/conversations.py - 대화 히스토리 API
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.conversation.repository import (
    ConversationRepository,
    ConversationLog,
    get_conversation_repository,
)

router = APIRouter(tags=["conversations"])


# ── 스키마 ───────────────────────────────────────────────────────
class ConversationLogResponse(BaseModel):
    id: int
    session_id: str
    knox_id: str
    chatbot_id: str
    user_message: str
    assistant_response: str
    tokens_used: int
    latency_ms: int
    search_results_count: int
    confidence_score: Optional[float]
    delegated_to: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ConversationStatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    avg_latency_ms: float
    avg_confidence: float
    total_tokens: int


# ── 의존성 ────────────────────────────────────────────────────────
def get_conv_repo() -> ConversationRepository:
    return get_conversation_repository()


# ── API 엔드포인트 ────────────────────────────────────────────────
@router.get("/api/conversations/session/{session_id}", response_model=List[ConversationLogResponse])
async def get_session_conversations(
    session_id: str,
    limit: int = Query(default=100, le=1000),
    repo: ConversationRepository = Depends(get_conv_repo),
):
    """세션별 대화 내역 조회"""
    logs = repo.get_by_session(session_id, limit)
    return [_to_response(log) for log in logs]


@router.get("/api/conversations/user/{knox_id}", response_model=List[ConversationLogResponse])
async def get_user_conversations(
    knox_id: str,
    limit: int = Query(default=100, le=1000),
    repo: ConversationRepository = Depends(get_conv_repo),
):
    """사용자별 대화 내역 조회"""
    logs = repo.get_by_user(knox_id, limit)
    return [_to_response(log) for log in logs]


@router.get("/api/conversations/chatbot/{chatbot_id}", response_model=List[ConversationLogResponse])
async def get_chatbot_conversations(
    chatbot_id: str,
    limit: int = Query(default=100, le=1000),
    repo: ConversationRepository = Depends(get_conv_repo),
):
    """챗봇별 대화 내역 조회"""
    logs = repo.get_by_chatbot(chatbot_id, limit)
    return [_to_response(log) for log in logs]


@router.get("/api/conversations/stats", response_model=ConversationStatsResponse)
async def get_conversation_stats(
    knox_id: Optional[str] = Query(default=None),
    repo: ConversationRepository = Depends(get_conv_repo),
):
    """대화 통계 조회"""
    stats = repo.get_stats(knox_id)
    return ConversationStatsResponse(**stats)


@router.get("/api/conversations/recent", response_model=List[ConversationLogResponse])
async def get_recent_conversations(
    limit: int = Query(default=20, le=100),
    repo: ConversationRepository = Depends(get_conv_repo),
):
    """최근 대화 내역 조회"""
    # Mock에서는 모든 로그를 시간순으로 반환
    logs = repo._logs if hasattr(repo, '_logs') else []
    logs = sorted(logs, key=lambda x: x.created_at, reverse=True)[:limit]
    return [_to_response(log) for log in logs]


# ── 헬퍼 함수 ─────────────────────────────────────────────────────
def _to_response(log: ConversationLog) -> ConversationLogResponse:
    return ConversationLogResponse(
        id=log.id,
        session_id=log.session_id,
        knox_id=log.knox_id,
        chatbot_id=log.chatbot_id,
        user_message=log.user_message,
        assistant_response=log.assistant_response[:200] + "..." if len(log.assistant_response) > 200 else log.assistant_response,
        tokens_used=log.tokens_used,
        latency_ms=log.latency_ms,
        search_results_count=log.search_results_count,
        confidence_score=log.confidence_score,
        delegated_to=log.delegated_to,
        created_at=log.created_at.isoformat(),
    )
