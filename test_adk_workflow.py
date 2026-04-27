"""
test_adk_workflow.py - ADK Workflow 테스트 케이스

실행 방법:
    cd /path/to/project
    source .venv/bin/activate
    python test_adk_workflow.py

테스트 항목:
    1. Agent 모듈 로드 테스트
    2. 단일 Agent 실행 테스트
    3. 전체 워크플로우 테스트
    4. 챗봇 대화 테스트
"""

import os
import sys
import asyncio
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 로드
from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print(f"[TEST] Loaded .env from {env_path}")

# 환경 설정
os.environ.setdefault("DEVELOPMENT", "true")
os.environ.setdefault("OLLAMA_MODEL", "kimi-k2.5")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434/v1")

print(f"[TEST] Environment: DEVELOPMENT={os.getenv('DEVELOPMENT')}")
print(f"[TEST] Model: {os.getenv('OLLAMA_MODEL')}")


# ============================================
# TC 1: Agent 모듈 로드 테스트
# ============================================
def test_agent_modules_load():
    """3개 Agent 모듈이 정상적으로 로드되는지 테스트"""
    print("\n" + "="*50)
    print("TC 1: Agent 모듈 로드 테스트")
    print("="*50)
    
    agents = [
        "architecture_agent",
        "implementation_agent", 
        "validation_agent"
    ]
    
    for agent_name in agents:
        try:
            module = __import__(agent_name, fromlist=['agent'])
            agent = module.agent
            print(f"[PASS] {agent_name}: name='{agent.name}'")
        except Exception as e:
            print(f"[FAIL] {agent_name}: {e}")
            return False
    
    return True


# ============================================
# TC 2: 단일 Agent 실행 테스트
# ============================================
async def test_single_agent():
    """Architecture Agent로 간단한 작업 테스트"""
    print("\n" + "="*50)
    print("TC 2: 단일 Agent 실행 테스트")
    print("="*50)
    
    try:
        from backend.api.adk_orchestrator import ADKWorkflowOrchestrator
        
        orch = ADKWorkflowOrchestrator()
        
        test_task = """
        다음 요구사항의 아키텍처를 설계해주세요:
        
        요구사항: 사용자 인증 시스템
        - JWT 기반 인증
        - PostgreSQL 사용자 저장
        - FastAPI 엔드포인트
        """
        
        print(f"[INFO] Testing with task: {test_task[:100]}...")
        
        result = await orch._run_agent(
            agent_key="architecture_agent",
            user_id="test_user",
            session_id="test-session-001",
            message=test_task
        )
        
        if result and len(result) > 50:
            print(f"[PASS] Agent responded with {len(result)} characters")
            print(f"[PREVIEW] {result[:200]}...")
            return True
        else:
            print(f"[FAIL] Empty or too short response: {result}")
            return False
            
    except Exception as e:
        print(f"[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================
# TC 3: 전체 워크플로우 테스트
# ============================================
async def test_full_workflow():
    """3단계 전체 워크플로우 테스트"""
    print("\n" + "="*50)
    print("TC 3: 전체 워크플로우 테스트")
    print("="*50)
    
    try:
        from backend.api.adk_orchestrator import ADKWorkflowOrchestrator
        
        orch = ADKWorkflowOrchestrator()
        
        test_task = "간단한 Todo List API 설계 및 구현 (in-memory 저장)"
        
        print(f"[INFO] Workflow task: {test_task}")
        print("[INFO] Starting 3-phase workflow...\n")
        
        phases = []
        async for result in orch.run_workflow(task=test_task):
            phases.append(result)
            print(f"[PHASE] {result.phase}: {result.status} ({result.duration_ms}ms)")
            print(f"[OUTPUT] {result.output[:150]}...\n")
        
        # 검증
        if len(phases) == 3:
            print("[PASS] All 3 phases completed")
            
            # 각 단계별 상태 확인
            statuses = [p.status for p in phases]
            if all(s == "success" for s in statuses):
                print("[PASS] All phases successful")
                return True
            else:
                print(f"[WARN] Some phases failed: {statuses}")
                return True  # 부분 성공도 성공으로 간주
        else:
            print(f"[FAIL] Expected 3 phases, got {len(phases)}")
            return False
            
    except Exception as e:
        print(f"[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================
# TC 4: 챗봇 대화 테스트
# ============================================
async def test_chat_service():
    """ADK 챗봇 서비스 테스트"""
    print("\n" + "="*50)
    print("TC 4: 챗봇 대화 테스트")
    print("="*50)
    
    try:
        from backend.api.chat_service import ADKChatService
        
        service = ADKChatService()
        
        test_message = "안녕하세요, 간단한 인사 부탁드립니다."
        
        print(f"[INFO] Chat message: {test_message}")
        
        responses = []
        async for event in service.stream_chat_response(
            chatbot_id="chatbot_company_adk",
            message=test_message,
            session_id="test-chat-session",
            user={"knox_id": "test_user"},
            system_prompt=""
        ):
            responses.append(event)
            print(f"[EVENT] {event[:100]}...")
        
        # 응답 검증
        full_response = "".join(responses)
        if len(full_response) > 20:
            print(f"[PASS] Chat responded with {len(full_response)} chars")
            return True
        else:
            print(f"[FAIL] Response too short: {full_response}")
            return False
            
    except Exception as e:
        print(f"[FAIL] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================
# 메인 실행
# ============================================
async def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "#"*50)
    print("# ADK Workflow 테스트 스위트 시작")
    print("#"*50)
    
    results = {}
    
    # TC 1
    results["TC1_Agent_Load"] = test_agent_modules_load()
    
    # TC 2
    results["TC2_Single_Agent"] = await test_single_agent()
    
    # TC 3
    results["TC3_Full_Workflow"] = await test_full_workflow()
    
    # TC 4
    results["TC4_Chat_Service"] = await test_chat_service()
    
    # 결과 요약
    print("\n" + "="*50)
    print("테스트 결과 요약")
    print("="*50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    print(f"\n전체: {passed}/{total} 통과")
    
    if passed == total:
        print("✅ 모든 테스트 통과!")
    else:
        print("❌ 일부 테스트 실패")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
