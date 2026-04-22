"""
backend/core/storage_backend.py - Storage Backend 추상화

SessionManager와 MemoryManager의 ADK/Fallback 듀얼 모드 중복 코드를 
추상화하여 제거하기 위한 Storage Backend ABC 클래스.

사용 예시:
    # Factory를 통해 구현체 자동 선택
    backend = StorageBackendFactory.create()
    
    # 또는 직접 구현체 사용
    from backend.adk.adk_storage_backend import ADKStorageBackend
    backend = ADKStorageBackend()
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional, Type

# Storage Backend 사용 여부 플래그 (USE_ADK와 동일하게 동작)
USE_ADK = os.environ.get("USE_ADK", "false").lower() == "true"


class StorageBackend(ABC):
    """
    Storage Backend 추상 기반 클래스.
    
    ADK와 인메모리 구현체의 공통 인터페이스를 정의합니다.
    모든 storage backend 구현체는 이 클래스를 상속받아야 합니다.
    """
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Backend가 사용 가능한지 확인.
        
        Returns:
            사용 가능한 경우 True
        """
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Backend 초기화.
        
        Returns:
            초기화 성공 여부
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Backend 종료 및 리소스 정리."""
        pass


class SessionStorageBackend(StorageBackend):
    """
    Session Storage Backend 추상 클래스.
    
    세션 관리를 위한 storage backend 인터페이스.
    """
    
    @abstractmethod
    def create_session(
        self,
        chatbot_id: str,
        user_knox_id: str,
        session_id: Optional[str] = None,
        role_override: Optional[dict[str, str]] = None,
        active_level: int = 1,
    ) -> "ChatSession":
        """새 세션을 생성합니다."""
        pass
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional["ChatSession"]:
        """세션 ID로 세션을 조회합니다."""
        pass
    
    @abstractmethod
    def find_recent_session(
        self,
        user_knox_id: str,
        chatbot_id: str,
    ) -> Optional["ChatSession"]:
        """동일 user + chatbot의 가장 최근 세션을 찾습니다."""
        pass
    
    @abstractmethod
    def close_session(self, session_id: str) -> bool:
        """세션을 종료하고 제거합니다."""
        pass
    
    @abstractmethod
    def list_sessions(self, user_knox_id: Optional[str] = None) -> list[dict]:
        """세션 목록을 조회합니다."""
        pass


class MemoryStorageBackend(StorageBackend):
    """
    Memory Storage Backend 추상 클래스.
    
    대화 메모리 관리를 위한 storage backend 인터페이스.
    """
    
    @abstractmethod
    def get_history(self, chatbot_id: str, session_id: str) -> list["Message"]:
        """지정된 챗봇/세션의 대화 기록을 반환합니다."""
        pass
    
    @abstractmethod
    def append(self, chatbot_id: str, session_id: str, message: "Message") -> None:
        """단일 메시지를 저장합니다."""
        pass
    
    @abstractmethod
    def append_pair(
        self,
        chatbot_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        max_messages: int = 20,
    ) -> None:
        """사용자 메시지와 어시스턴트 메시지를 함께 저장하고 길이를 제한합니다."""
        pass
    
    @abstractmethod
    def clear(self, chatbot_id: str, session_id: str) -> None:
        """지정된 챗봇/세션의 대화 기록을 삭제합니다."""
        pass
    
    @abstractmethod
    def clear_all_for_session(self, session_id: str) -> None:
        """특정 세션에 속한 모든 챗봇 메모리를 삭제합니다."""
        pass
    
    @abstractmethod
    def get_all_keys(self) -> list[tuple[str, str]]:
        """디버깅용: 저장된 모든 키를 반환합니다."""
        pass


class StorageBackendFactory:
    """
    Storage Backend Factory.
    
    USE_ADK 환경변수에 따라 자동으로 적절한 storage backend 구현체를 생성합니다.
    """
    
    _session_backend: Optional[SessionStorageBackend] = None
    _memory_backend: Optional[MemoryStorageBackend] = None
    
    @classmethod
    def create_session_backend(
        cls,
        force_adk: bool = False,
        force_inmemory: bool = False,
    ) -> SessionStorageBackend:
        """
        Session Storage Backend를 생성합니다.
        
        Args:
            force_adk: ADK 구현체를 강제 사용
            force_inmemory: 인메모리 구현체를 강제 사용
            
        Returns:
            SessionStorageBackend 인스턴스
        """
        from backend.core.inmemory_storage_backend import InMemorySessionStorage
        
        use_adk = (USE_ADK or force_adk) and not force_inmemory
        
        if use_adk:
            try:
                from backend.adk.adk_storage_backend import ADKSessionStorage
                backend = ADKSessionStorage()
                if backend.initialize():
                    return backend
            except Exception:
                pass
        
        # Fallback: 인메모리 구현체
        backend = InMemorySessionStorage()
        backend.initialize()
        return backend
    
    @classmethod
    def create_memory_backend(
        cls,
        force_adk: bool = False,
        force_inmemory: bool = False,
    ) -> MemoryStorageBackend:
        """
        Memory Storage Backend를 생성합니다.
        
        Args:
            force_adk: ADK 구현체를 강제 사용
            force_inmemory: 인메모리 구현체를 강제 사용
            
        Returns:
            MemoryStorageBackend 인스턴스
        """
        from backend.core.inmemory_storage_backend import InMemoryMemoryStorage
        
        use_adk = (USE_ADK or force_adk) and not force_inmemory
        
        if use_adk:
            try:
                from backend.adk.adk_storage_backend import ADKMemoryStorage
                backend = ADKMemoryStorage()
                if backend.initialize():
                    return backend
            except Exception:
                pass
        
        # Fallback: 인메모리 구현체
        backend = InMemoryMemoryStorage()
        backend.initialize()
        return backend
    
    @classmethod
    def reset(cls) -> None:
        """Factory 상태를 초기화합니다 (테스트용)."""
        cls._session_backend = None
        cls._memory_backend = None


# 타입 힌트를 위한 전방 선언 (실제 구현에서 import)
# 이 주석은 순환 import 방지를 위해 필요함
# from backend.core.models import ChatSession, Message