"""
ADK 디버그 환경 검증 스크립트
"""
import os
import sys
import logging

# 디버그 환경 설정
os.environ['ADK_DEBUG'] = '1'
os.environ['LOG_LEVEL'] = 'DEBUG'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("=" * 60)
print("ADK 디버그 환경 검증")
print("=" * 60)

# 1. ADK 버전 확인
print("\n1. ADK 버전 확인...")
try:
    import google.adk
    print(f"   ✅ ADK 버전: {google.adk.__version__}")
except AttributeError:
    print("   ⚠️  버전 정보 없음")
except ImportError as e:
    print(f"   ❌ ADK import 실패: {e}")

# 2. SessionService 확인
print("\n2. SessionService 검증...")
try:
    from google.adk.sessions import Session
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    service = InMemorySessionService()
    print("   ✅ InMemorySessionService 생성 성공")
    
    # 세션 생성 테스트
    session = service.create_session(
        app_name="debug_test",
        user_id="test_user",
        session_id="test_session_001",
        state={"test": "value"}
    )
    print(f"   ✅ 세션 생성: {session.session_id}")
    print(f"   📋 세션 상태: {session.state}")
except Exception as e:
    print(f"   ❌ 실패: {e}")

# 3. ADK 설정 확인
print("\n3. ADK 설정 검증...")
try:
    from config import settings
    print(f"   ✅ 설정 로드 성공")
    print(f"   📋 USE_ADK: {getattr(settings, 'USE_ADK', 'N/A')}")
except Exception as e:
    print(f"   ⚠️  설정 로드 실패: {e}")

# 4. 커스텀 Backend 검증
print("\n4. ADK Storage Backend 검증...")
try:
    from backend.adk.adk_storage_backend import ADKSessionStorage, ADKMemoryStorage
    
    session_storage = ADKSessionStorage()
    session_storage.initialize()
    print("   ✅ ADKSessionStorage 초기화 성공")
    
    memory_storage = ADKMemoryStorage()
    memory_storage.initialize()
    print("   ✅ ADKMemoryStorage 초기화 성공")
    
    # 세션 생성 테스트
    chat_session = session_storage.create_session(
        chatbot_id="debug-bot",
        user_knox_id="debug-user"
    )
    print(f"   ✅ 세션 생성: {chat_session.session_id}")
    
    # 메모리 저장 테스트
    memory_storage.append_message("debug-bot", chat_session.session_id, {
        "role": "user",
        "content": "테스트 메시지"
    })
    print("   ✅ 메모리 저장 성공")
    
    # 조회 테스트
    history = memory_storage.get_history("debug-bot", chat_session.session_id)
    print(f"   ✅ 메모리 조회: {len(history)}개 메시지")
    
except Exception as e:
    print(f"   ❌ 실패: {e}")
    import traceback
    traceback.print_exc()

# 5. Executor 검증
print("\n5. HierarchicalAgentExecutor 검증...")
try:
    from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
    from backend.core.models import ChatbotDef, ExecutionRole
    from backend.retrieval.ingestion_client import IngestionClient
    from backend.managers.memory_manager import MemoryManager
    
    # 테스트용 ChatbotDef 생성
    chatbot_def = ChatbotDef(
        id="debug-bot",
        name="Debug Bot",
        level=0,
        system_prompt="You are a helpful assistant.",
        role=ExecutionRole.AGENT,
        retrieval={"db_ids": ["test"], "k": 3},
        memory={"max_messages": 10},
        policy={"delegation_threshold": 70}
    )
    
    ingestion = IngestionClient(base_url="http://localhost:8001")
    memory = MemoryManager()
    
    executor = HierarchicalAgentExecutor(
        chatbot_def=chatbot_def,
        ingestion_client=ingestion,
        memory_manager=memory
    )
    print("   ✅ HierarchicalAgentExecutor 생성 성공")
    
    # Confidence 계산 테스트
    confidence = executor._calculate_confidence("테스트 컨텍스트", "테스트 메시지")
    print(f"   ✅ _calculate_confidence: {confidence}")
    
except Exception as e:
    print(f"   ❌ 실패: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("검증 완료")
print("=" * 60)
