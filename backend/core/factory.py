from __future__ import annotations
"""
core/factory.py - Factory Method: 런타임 실행 컨텍스트 생성
요청이 들어올 때마다 챗봇 정의 + 세션 + 권한 정보를 조합하여
ExecutionContext를 생성한다.
"""
from backend.core.models import (
    ChatbotDef,
    ChatSession,
    ExecutionContext,
    ExecutionRole,
    Message,
)
from backend.managers.memory_manager import MemoryManager


def create_execution_context(
    chatbot_def: ChatbotDef,
    session: ChatSession,
    user_db_scope: set[str],
    memory_manager: MemoryManager,
) -> ExecutionContext:
    """
    Parameters
    ----------
    chatbot_def:    등록된 챗봇 정의
    session:        현재 세션 (세션 역할 오버라이드 포함)
    user_db_scope:  사용자에게 허용된 db_ids 집합
    memory_manager: 대화 메모리를 관리하는 매니저

    Returns
    -------
    ExecutionContext: 실행 준비가 완료된 컨텍스트
    """
    # 1. 데이터 소스 권한 교집합 (보안 경계)
    chatbot_scope = set(chatbot_def.retrieval.db_ids)
    authorized_db_ids = list(chatbot_scope & user_db_scope)

    # 2. 실행 역할 결정 (세션 오버라이드 우선)
    effective_role = session.role_override.get(chatbot_def.id, chatbot_def.role)

    # 3. 대화 기록 복원
    history = memory_manager.get_history(
        chatbot_id=chatbot_def.id,
        session_id=session.session_id,
    )

    return ExecutionContext(
        chatbot_def=chatbot_def,
        session=session,
        authorized_db_ids=authorized_db_ids,
        effective_role=effective_role,
        history=history,
    )
