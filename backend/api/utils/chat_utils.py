"""
backend/api/utils/chat_utils.py - 채팅 API 유틸리티
"""
from __future__ import annotations

from fastapi import Request, HTTPException
from typing import Optional, List

from backend.config import settings
from backend.core.models import ExecutionRole
from backend.managers.chatbot_manager import ChatbotManager
from backend.managers.memory_manager import MemoryManager
from backend.managers.session_manager import SessionManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.executors import ToolExecutor, HierarchicalAgentExecutor


def get_chatbot_manager(request: Request) -> ChatbotManager:
    """Request 앱 상태에서 ChatbotManager 반환"""
    return request.app.state.chatbot_manager


def get_session_manager(request: Request) -> SessionManager:
    """Request 앱 상태에서 SessionManager 반환"""
    return request.app.state.session_manager


def get_memory_manager(request: Request) -> MemoryManager:
    """Request 앱 상태에서 MemoryManager 반환"""
    return request.app.state.memory_manager


def get_ingestion_client(request: Request) -> IngestionClient:
    """Request 앱 상태에서 IngestionClient 반환"""
    return request.app.state.ingestion_client


def resolve_execution_mode(
    chatbot_def,
    session,
    requested_mode: Optional[str] = None,
) -> ExecutionRole:
    """
    실행 모드 결정 (요청 > 세션 > 챗봇 기본값)

    Args:
        chatbot_def: 챗봇 정의 객체
        session: 세션 객체
        requested_mode: 요청된 모드 (None 가능)

    Returns:
        ExecutionRole: 결정된 실행 역할
    """
    mode_str = requested_mode

    if not mode_str and session.role_override:
        mode_str = session.role_override.get(chatbot_def.id)

    if not mode_str:
        mode_str = chatbot_def.role.value

    try:
        return ExecutionRole(mode_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"잘못된 mode: {mode_str}"
        )


def create_executor(
    mode: ExecutionRole,
    chatbot_def,
    ingestion_client: IngestionClient,
    memory_manager: MemoryManager,
    chatbot_manager: Optional[ChatbotManager] = None,
):
    """
    모드에 맞는 Executor 생성

    Args:
        mode: 실행 모드
        chatbot_def: 챗봇 정의
        ingestion_client: 문서 임베딩 클라이언트
        memory_manager: 메모리 관리자
        chatbot_manager: 챗봇 관리자 (Agent 모드 필요)

    Returns:
        ToolExecutor or HierarchicalAgentExecutor
    """
    if mode == ExecutionRole.TOOL:
        return ToolExecutor(chatbot_def, ingestion_client)

    return HierarchicalAgentExecutor(
        chatbot_def=chatbot_def,
        ingestion_client=ingestion_client,
        memory_manager=memory_manager,
        chatbot_manager=chatbot_manager,
        accumulated_context="",
        delegation_depth=0,
    )


def authorize_chatbot_dbs(
    chatbot_def,
    user_permissions: dict,
    chatbot_id: str,
    user_db_scope: set,
) -> List[str]:
    """
    챗봇 DB 접근 권한 검증

    Args:
        chatbot_def: 챗봇 정의
        user_permissions: 사용자 챗봇 권한
        chatbot_id: 챗봇 ID
        user_db_scope: 사용자 DB 접근 범위

    Returns:
        List[str]: 허가된 DB ID 목록

    Raises:
        HTTPException: 권한 없음 시 403
    """
    from backend.api.middleware.auth_middleware import check_chatbot_access
    from backend.debug_logger import logger

    requested_db_ids = chatbot_def.retrieval.db_ids

    if not check_chatbot_access(user_permissions, chatbot_id):
        raise HTTPException(
            status_code=403,
            detail=f"해당 챗봇에 접근할 권한이 없습니다: {chatbot_id}"
        )

    # 사용자 DB 스코프와 챗봇 DB의 교집합 계산
    authorized_db_ids = [
        db_id for db_id in requested_db_ids
        if db_id in user_db_scope or settings.USE_MOCK_AUTH
    ]

    if not authorized_db_ids and requested_db_ids:
        missing_dbs = set(requested_db_ids) - user_db_scope
        logger.error(f"[authorize_chatbot_dbs] 사용자의 DB 접근 권한 없음: {missing_dbs}")
        raise HTTPException(
            status_code=403,
            detail=f"해당 챗봇에 접근할 수 있는 데이터베이스 권한이 없습니다."
        )

    return authorized_db_ids
