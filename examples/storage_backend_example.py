"""
Storage Backend 추상화 사용 예시

이 파일은 Storage Backend 추상화를 사용하는 방법을 보여줍니다.
"""

from __future__ import annotations

import os

# USE_ADK 환경변수에 따라 자동으로 구현체 선택
# USE_ADK=true -> ADK 구현체 사용
# USE_ADK=false -> 인메모리 구현체 사용 (기본값)
os.environ['USE_ADK'] = 'false'

from backend.core.storage_backend import StorageBackendFactory
from backend.managers.session_manager import SessionManager
from backend.managers.memory_manager import MemoryManager
from backend.core.models import Message


def main():
    print("Storage Backend 추상화 예시")
    print("=" * 60)
    
    # 방법 1: Factory를 통해 Storage Backend 생성 (권장)
    print("\n1. Factory를 통한 Session Backend 생성")
    session_backend = StorageBackendFactory.create_session_backend()
    print(f"   선택된 구현체: {type(session_backend).__name__}")
    
    print("\n2. Factory를 통한 Memory Backend 생성")
    memory_backend = StorageBackendFactory.create_memory_backend()
    print(f"   선택된 구현체: {type(memory_backend).__name__}")
    
    # 방법 2: Manager를 통해 자동 생성 (더 간단)
    print("\n3. SessionManager 자동 생성")
    session_mgr = SessionManager()
    print(f"   내부 구현체: {type(session_mgr._backend).__name__}")
    
    print("\n4. MemoryManager 자동 생성")
    memory_mgr = MemoryManager()
    print(f"   내부 구현체: {type(memory_mgr._backend).__name__}")
    
    # 세션 작업 예시
    print("\n5. 세션 작업")
    session = session_mgr.create_session(
        chatbot_id="my_chatbot",
        user_knox_id="user_123",
        session_id="demo_session_001",
        role_override={"bot1": "AGENT", "bot2": "OBSERVER"},
        active_level=2,
    )
    print(f"   생성된 세션: {session.session_id}")
    print(f"   챗봇 ID: {session.chatbot_id}")
    print(f"   사용자 Knox ID: {session.user_knox_id}")
    print(f"   활성 레벨: {session.active_level}")
    
    # 메모리 작업 예시
    print("\n6. 메모리 작업")
    memory_mgr.append_pair(
        chatbot_id="my_chatbot",
        session_id=session.session_id,
        user_content="안녕하세요!",
        assistant_content="안녕하세요! 무엇을 도와드릴까요?",
    )
    print(f"   메시지 쌍 추가 완료")
    
    history = memory_mgr.get_history("my_chatbot", session.session_id)
    print(f"   대화 기록: {len(history)}개 메시지")
    for msg in history:
        print(f"   - [{msg.role}]: {msg.content}")
    
    # 정리
    print("\n7. 리소스 정리")
    session_mgr.shutdown()
    memory_mgr.shutdown()
    print(f"   모든 Manager 종료 완료")
    
    print("\n" + "=" * 60)
    print("예시 완료!")


def example_with_explicit_backend():
    """
    명시적 Backend 선택 예시
    테스트나 특정 구현체를 강제로 사용할 때 유용
    """
    from backend.core.inmemory_storage_backend import (
        InMemorySessionStorage,
        InMemoryMemoryStorage,
    )
    
    print("\n명시적 Backend 선택 예시")
    print("=" * 60)
    
    # 직접 인메모리 구현체 사용
    session_backend = InMemorySessionStorage()
    session_backend.initialize()
    
    memory_backend = InMemoryMemoryStorage()
    memory_backend.initialize()
    
    # Manager에 주입
    session_mgr = SessionManager(backend=session_backend)
    memory_mgr = MemoryManager(backend=memory_backend)
    
    print(f"Session Backend: {type(session_mgr._backend).__name__}")
    print(f"Memory Backend: {type(memory_mgr._backend).__name__}")
    
    session_mgr.shutdown()
    memory_mgr.shutdown()
    
    print("완료!")


if __name__ == "__main__":
    main()
    example_with_explicit_backend()