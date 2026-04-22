"""
backend/core/inmemory_storage_backend.py - In-Memory Storage Backend

인메모리 기반의 Storage Backend 구현체.
USE_ADK=false 시 또는 ADK 사용 불가 시 fallback으로 사용됩니다.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Optional

from backend.core.storage_backend import SessionStorageBackend, MemoryStorageBackend
from backend.core.models import ChatSession, ExecutionRole, Message

logger = logging.getLogger(__name__)


class InMemorySessionStorage(SessionStorageBackend):
    """
    인메모리 기반 Session Storage Backend.
    """
    
    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}
        self._initialized = False
    
    def is_available(self) -> bool:
        """인메모리 backend는 항상 사용 가능합니다."""
        return True
    
    def initialize(self) -> bool:
        """인메모리 저장소를 초기화합니다."""
        self._sessions = {}
        self._initialized = True
        logger.info("[InMemorySessionStorage] Initialized")
        return True
    
    def shutdown(self) -> None:
        """인메모리 저장소를 종료합니다."""
        self._sessions.clear()
        self._initialized = False
        logger.info("[InMemorySessionStorage] Shutdown")
    
    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> ChatSession:
        """새 세션을 생성합니다."""
        sid = session_id or str(uuid.uuid4())
        
        # role_override 변환 (str -> ExecutionRole)
        overrides: dict[str, ExecutionRole] = {}
        if role_override:
            for bot_id, role_str in role_override.items():
                try:
                    overrides[bot_id] = ExecutionRole(role_str)
                except ValueError:
                    overrides[bot_id] = ExecutionRole.AGENT
        
        session = ChatSession(
            session_id=sid,
            chatbot_id=chatbot_id,
            user_knox_id=user_knox_id,
            role_override=overrides,
            active_level=active_level,
        )
        self._sessions[sid] = session
        logger.info(f"[InMemorySessionStorage] Created session: {sid}")
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """세션 ID로 세션을 조회합니다."""
        return self._sessions.get(session_id)
    
    def find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional[ChatSession]:
        """동일 user + chatbot의 가장 최근 세션을 찾습니다."""
        matching = [
            s for s in self._sessions.values()
            if s.user_knox_id == user_knox_id and s.chatbot_id == chatbot_id
        ]
        if matching:
            return matching[-1]  # 가장 마지막에 추가된 세션
        return None
    
    def close_session(self, session_id: str) -> bool:
        """세션을 종료하고 제거합니다."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[InMemorySessionStorage] Closed session: {session_id}")
            return True
        return False
    
    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """세션 목록을 조회합니다."""
        sessions = self._sessions.values()
        if user_knox_id:
            sessions = [s for s in sessions if s.user_knox_id == user_knox_id]
        return [s.to_dict() for s in sessions]


class InMemoryMemoryStorage(MemoryStorageBackend):
    """
    인메모리 기반 Memory Storage Backend.
    
    (chatbot_id, session_id) 튜플을 키로 사용하여
    각 챗봇/세션 조합별로 완전히 격리된 대화 기록을 유지합니다.
    """
    
    def __init__(self):
        self._store: dict[tuple[str, str], list[Message]] = {}
        self._initialized = False
    
    def _key(self, chatbot_id: str, session_id: str) -> tuple[str, str]:
        """내부 저장용 키를 생성합니다."""
        return (chatbot_id, session_id)
    
    def is_available(self) -> bool:
        """인메모리 backend는 항상 사용 가능합니다."""
        return True
    
    def initialize(self) -> bool:
        """인메모리 저장소를 초기화합니다."""
        self._store = {}
        self._initialized = True
        logger.info("[InMemoryMemoryStorage] Initialized")
        return True
    
    def shutdown(self) -> None:
        """인메모리 저장소를 종료합니다."""
        self._store.clear()
        self._initialized = False
        logger.info("[InMemoryMemoryStorage] Shutdown")
    
    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        """지정된 챗봇/세션의 대화 기록을 반환합니다."""
        return list(self._store.get(self._key(chatbot_id, session_id), []))
    
    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
        """단일 메시지를 저장합니다."""
        key = self._key(chatbot_id, session_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(message)
    
    def append_pair(
        self,
        chatbot_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        max_messages: int = 20,
    ) -> None:
        """사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한합니다."""
        key = self._key(chatbot_id, session_id)
        if key not in self._store:
            self._store[key] = []
        
        self._store[key].append(Message(role="user", content=user_content))
        self._store[key].append(Message(role="assistant", content=assistant_content))
        
        # 최대 메시지 수 유지 (오래된 것부터 제거, 최소 단위 2개씩)
        if max_messages > 0 and len(self._store[key]) > max_messages:
            excess = len(self._store[key]) - max_messages
            # 짝수 단위로 제거해 user/assistant 쌍을 보존
            if excess % 2 != 0:
                excess += 1
            self._store[key] = self._store[key][excess:]
    
    def clear(self, chatbot_id: str, session_id: str) -> None:
        """지정된 챗봇/세션의 대화 기록을 삭제합니다."""
        self._store.pop(self._key(chatbot_id, session_id), None)
    
    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제합니다."""
        keys_to_remove = [k for k in self._store if k[1] == session_id]
        for k in keys_to_remove:
            del self._store[k]
    
    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버깅용: 저장된 모든 키를 반환합니다."""
        return list(self._store.keys())