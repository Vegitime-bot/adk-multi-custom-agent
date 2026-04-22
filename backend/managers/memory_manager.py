"""
managers/memory_manager.py - 대화 메모리 관리 (Storage Backend 추상화 적용)

StorageBackend 추상화를 사용하여 ADK/인메모리 듀얼 모드를 관리합니다.
USE_ADK 환경변수에 따라 자동으로 구현체가 선택됩니다.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.core.models import Message
from backend.core.storage_backend import (
    MemoryStorageBackend,
    StorageBackendFactory,
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    대화 메모리 관리자.
    
    StorageBackend 추상화를 통해 ADK/인메모리 구현을 투명하게 처리합니다.
    """
    
    def __init__(self, backend: Optional[MemoryStorageBackend] = None):
        """
        MemoryManager를 초기화합니다.
        
        Args:
            backend: 사용할 MemoryStorageBackend (None이면 Factory에서 자동 생성)
        """
        if backend is None:
            self._backend = StorageBackendFactory.create_memory_backend()
        else:
            self._backend = backend
        
        logger.info(f"[MemoryManager] Initialized with {type(self._backend).__name__}")
    
    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        """지정된 챗봇/세션의 대화 기록을 반환합니다."""
        return self._backend.get_history(chatbot_id, session_id)
    
    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
        """단일 메시지를 저장합니다."""
        self._backend.append(chatbot_id, session_id, message)
    
    def append_pair(
        self,
        chatbot_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        max_messages: int = 20,
    ) -> None:
        """
        사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한합니다.
        """
        self._backend.append_pair(
            chatbot_id=chatbot_id,
            session_id=session_id,
            user_content=user_content,
            assistant_content=assistant_content,
            max_messages=max_messages,
        )
    
    def clear(self, chatbot_id: str, session_id: str) -> None:
        """지정된 챗봇/세션의 대화 기록을 삭제합니다."""
        self._backend.clear(chatbot_id, session_id)
    
    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제합니다."""
        self._backend.clear_all_for_session(session_id)
    
    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버깅용: 저장된 모든 키를 반환합니다."""
        return self._backend.get_all_keys()
    
    def shutdown(self) -> None:
        """MemoryManager를 종료하고 리소스를 정리합니다."""
        self._backend.shutdown()
        logger.info("[MemoryManager] Shutdown")