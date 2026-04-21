from __future__ import annotations
"""
managers/memory_manager.py - 대화 메모리 관리
챗봇/세션 단위로 격리된 인메모리 대화 기록을 관리한다.
키: (chatbot_id, session_id) → 격리 원칙 유지
향후 Redis / 외부 DB로 교체 가능.
"""
from backend.core.models import Message


class MemoryManager:
    def __init__(self):
        # { (chatbot_id, session_id): [Message, ...] }
        self._store: dict[tuple[str, str], list[Message]] = {}

    def _key(self, chatbot_id: str, session_id: str) -> tuple[str, str]:
        return (chatbot_id, session_id)

    def get_history(self, chatbot_id: str, session_id: str) -> list[Message]:
        return list(self._store.get(self._key(chatbot_id, session_id), []))

    def append(self, chatbot_id: str, session_id: str, message: Message) -> None:
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
        self._store.pop(self._key(chatbot_id, session_id), None)

    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제한다."""
        keys_to_remove = [k for k in self._store if k[1] == session_id]
        for k in keys_to_remove:
            del self._store[k]

    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버그용: 저장된 모든 키 반환"""
        return list(self._store.keys())
