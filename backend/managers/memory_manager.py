from __future__ import annotations
"""
managers/memory_manager.py - 대화 메모리 관리 (ADK 마이그레이션 완료)

ADK Memory를 사용하여 대화 기록을 관리합니다.
USE_ADK=false 시 기존 인메모리 구현으로 fallback.
"""
from typing import Optional

from backend.core.models import Message

# ADK Memory 래퍼 import
try:
    from backend.adk.adk_memory_wrapper import ADKMemoryWrapper, USE_ADK
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    USE_ADK = False


class MemoryManager:
    def __init__(self):
        self._use_adk = USE_ADK and ADK_AVAILABLE
        self._adk_wrapper: Optional[ADKMemoryWrapper] = None
        self._store: dict[tuple[str, str], list[Message]] = {}  # Fallback용
        
        if self._use_adk:
            try:
                self._adk_wrapper = ADKMemoryWrapper()
            except Exception:
                self._use_adk = False

    def _key(self, chatbot_id: str, session_id: str) -> tuple[str, str]:
        return (chatbot_id, session_id)

    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.get_history(chatbot_id, session_id)
        return list(self._store.get(self._key(chatbot_id, session_id), []))

    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
        if self._use_adk and self._adk_wrapper:
            self._adk_wrapper.append(chatbot_id, session_id, message)
            return
            
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
        """사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한한다."""
        if self._use_adk and self._adk_wrapper:
            self._adk_wrapper.append_pair(
                chatbot_id, session_id,
                user_content, assistant_content,
                max_messages=max_messages
            )
            return
        
        # Fallback: 기존 인메모리 구현
        key = self._key(chatbot_id, session_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(Message(role="user", content=user_content))
        self._store[key].append(Message(role="assistant", content=assistant_content))
        
        # 최대 메시지 수 유지
        if max_messages > 0 and len(self._store[key]) > max_messages:
            excess = len(self._store[key]) - max_messages
            if excess % 2 != 0:
                excess += 1
            self._store[key] = self._store[key][excess:]

    def clear(self, chatbot_id: str, session_id: str) -> None:
        if self._use_adk and self._adk_wrapper:
            self._adk_wrapper.clear(chatbot_id, session_id)
            return
        self._store.pop(self._key(chatbot_id, session_id), None)

    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제한다."""
        if self._use_adk and self._adk_wrapper:
            self._adk_wrapper.clear_all_for_session(session_id)
            return
            
        keys_to_remove = [k for k in self._store if k[1] == session_id]
        for k in keys_to_remove:
            del self._store[k]

    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버그용: 저장된 모든 키 반환"""
        if self._use_adk and self._adk_wrapper:
            return self._adk_wrapper.get_all_keys()
        return list(self._store.keys())
