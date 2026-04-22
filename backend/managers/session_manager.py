from __future__ import annotations
"""
managers/session_manager.py - 세션 관리 (ADK 마이그레이션 완료)

ADK Session을 사용하여 세션 관리를 수행합니다.
USE_ADK=false 시 기존 인메모리 구현으로 fallback.
"""
import uuid
import logging
from typing import Optional

from backend.core.models import ChatSession, ExecutionRole

# ADK Session 래퍼 import
try:
    from backend.adk.adk_session_wrapper import ADKSessionWrapper, USE_ADK
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    USE_ADK = False

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self):
        self._use_adk = USE_ADK and ADK_AVAILABLE
        self._adk_wrapper: Optional[ADKSessionWrapper] = None
        self._sessions: dict[str, ChatSession] = {}  # Fallback용
        
        if self._use_adk:
            try:
                self._adk_wrapper = ADKSessionWrapper()
                logger.info("[SessionManager] ADK Session initialized")
            except Exception as e:
                logger.warning(f"[SessionManager] ADK init failed, using fallback: {e}")
                self._use_adk = False
        
        if not self._use_adk:
            logger.info("[SessionManager] Using in-memory fallback")

    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> ChatSession:
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.create_session(
                chatbot_id=chatbot_id,
                user_knox_id=user_knox_id,
                session_id=session_id,
                role_override=role_override,
                active_level=active_level,
            )
        
        # Fallback: 기존 인메모리 구현
        sid = session_id or str(uuid.uuid4())
        overrides: dict[str, ExecutionRole] = {}
        if role_override:
            for bot_id, role_str in role_override.items():
                overrides[bot_id] = ExecutionRole(role_str)

        session = ChatSession(
            session_id=sid,
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            role_override=overrides,
            active_level=active_level,
        )
        self._sessions[sid] = session
        logger.info(f"[SessionManager] Created session: {sid}")
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.get_session(session_id)
        return self._sessions.get(session_id)

    def get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """세션 조회 또는 생성. session_id가 없으면 최근 세션 자동 연결."""
        # 1. 명시적 session_id로 조회
        if session_id:
            existing = self.get_session(session_id)
            if existing:
                logger.info(f"[SessionManager] Found existing session: {session_id}")
                return existing
        
        # 2. ADK 사용 시 ADK에서 최근 세션 찾기
        if self._use_adk and self._adk_wrapper:
            recent = self._adk_wrapper.find_recent_session(user_knox_id, chatbot_id)
            if recent:
                logger.info(f"[SessionManager] Reusing ADK session: {recent.session_id}")
                return recent
        
        # 3. Fallback: 동일 user + chatbot의 최근 세션 찾기
        if not self._use_adk:
            recent_session = self._find_recent_session(user_knox_id, chatbot_id)
            if recent_session:
                logger.info(f"[SessionManager] Reusing recent session: {recent_session.session_id}")
                return recent_session
        
        # 4. 새 세션 생성
        new_session = self.create_session(
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            session_id=session_id,
        )
        logger.info(f"[SessionManager] Created new session: {new_session.session_id}")
        return new_session
    
    def _find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """Fallback: 동일 user + chatbot의 가장 최근 세션 찾기"""
        matching = [
            s for s in self._sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            return matching[-1]
        return None

    def close_session(self, session_id: str) -> bool:
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.close_session(session_id)
        
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.list_sessions(user_knox_id)
        
        sessions = self._sessions.values()
        if user_knox_id:
            sessions = [s for s in sessions if s.user_knox_id == user_knox_id]
        return [s.to_dict() for s in sessions]
