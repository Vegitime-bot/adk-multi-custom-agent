"""
managers/session_manager.py - 세션 관리 (Storage Backend 추상화 적용)

StorageBackend 추상화를 사용하여 ADK/인메모리 듀얼 모드를 관리합니다.
USE_ADK 환경변수에 따라 자동으로 구현체가 선택됩니다.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.core.models import ChatSession
from backend.core.storage_backend import (
    SessionStorageBackend,
    StorageBackendFactory,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """
    세션 관리자.
    
    StorageBackend 추상화를 통해 ADK/인메모리 구현을 투명하게 처리합니다.
    """
    
    def __init__(self, backend: Optional[SessionStorageBackend] = None):
        """
        SessionManager를 초기화합니다.
        
        Args:
            backend: 사용할 SessionStorageBackend (None이면 Factory에서 자동 생성)
        """
        if backend is None:
            self._backend = StorageBackendFactory.create_session_backend()
        else:
            self._backend = backend
        
        logger.info(f"[SessionManager] Initialized with {type(self._backend).__name__}")
    
    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> ChatSession:
        """새 세션을 생성합니다."""
        return self._backend.create_session(
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            session_id=session_id,
            role_override=role_override,
            active_level=active_level,
        )
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """세션 ID로 세션을 조회합니다."""
        return self._backend.get_session(session_id)
    
    def get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """
        세션을 조회하거나 생성합니다.
        session_id가 없으면 최근 세션을 자동으로 연결합니다.
        """
        # 1. 명시적 session_id로 조회
        if session_id:
            existing = self.get_session(session_id)
            if existing:
                logger.info(f"[SessionManager] Found existing session: {session_id}")
                return existing
        
        # 2. 최근 세션 찾기
        recent = self._backend.find_recent_session(user_knox_id, chatbot_id)
        if recent:
            logger.info(f"[SessionManager] Reusing recent session: {recent.session_id}")
            return recent
        
        # 3. 새 세션 생성
        new_session = self.create_session(
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            session_id=session_id,
        )
        logger.info(f"[SessionManager] Created new session: {new_session.session_id}")
        return new_session
    
    def close_session(self, session_id: str) -> bool:
        """세션을 종료하고 제거합니다."""
        return self._backend.close_session(session_id)
    
    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """세션 목록을 조회합니다."""
        return self._backend.list_sessions(user_knox_id)
    
    def shutdown(self) -> None:
        """SessionManager를 종료하고 리소스를 정리합니다."""
        self._backend.shutdown()
        logger.info("[SessionManager] Shutdown")