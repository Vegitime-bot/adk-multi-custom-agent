from __future__ import annotations
"""
managers/session_manager.py - 세션 관리
세션 생성/조회/종료와 세션별 역할 오버라이드를 관리한다.
현재 인메모리 구현 (향후 Redis/DB로 교체 가능).
"""
import uuid
import logging
from backend.core.models import ChatSession, ExecutionRole

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: str | None = None,
        role_override: dict[str, str] | None = None,
        active_level: int = 1,
    ) -> ChatSession:
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
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def get_or_create(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: str | None = None,
    ) -> ChatSession:
        """세션 조회 또는 생성. session_id가 없으면 최근 세션 자동 연결."""
        # 1. 명시적 session_id로 조회
        if session_id and session_id in self._sessions:
            logger.info(f"[SessionManager] Found existing session: {session_id}")
            return self._sessions[session_id]
        
        # 2. 동일 user + chatbot의 최근 세션 찾기
        recent_session = self._find_recent_session(user_knox_id, chatbot_id)
        if recent_session:
            logger.info(f"[SessionManager] Reusing recent session: {recent_session.session_id} for {user_knox_id}/{chatbot_id}")
            return recent_session
        
        # 3. 새 세션 생성
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
    ) -> ChatSession | None:
        """동일 user + chatbot의 가장 최근 세션 찾기"""
        matching = [
            s for s in self._sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            # 생성 시간 기준으로 정렬 (session_id가 uuid이므로 대략적인 시간순)
            # 더 정확하려면 ChatSession에 created_at 필드 필요
            return matching[-1]  # 가장 마지막에 추가된 세션
        return None

    def close_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self, user_knox_id: str | None = None) -> list[dict]:
        sessions = self._sessions.values()
        if user_knox_id:
            sessions = [s for s in sessions if s.user_knox_id == user_knox_id]
        return [s.to_dict() for s in sessions]
