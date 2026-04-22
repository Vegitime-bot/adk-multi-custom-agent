"""
test_circuit_breaker_integration.py - Circuit Breaker 통합 테스트

위임 체인에서 Circuit Breaker가 실제로 동작하는지 검증합니다.

실행 방법:
    python tests/test_circuit_breaker_integration.py
"""
import sys
import time
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    DelegationCircuitBreakerManager,
)


def test_delegation_circuit_breaker():
    """
    위임 체인에서 Circuit Breaker 통합 테스트
    
    시나리오:
    1. Agent A에서 Agent B로 위임
    2. Agent B가 연속 실패
    3. Circuit Breaker가 OPEN 상태로 전환
    4. 후속 위임은 바로 fallback 반환
    5. 복구 시간 후 HALF_OPEN 상태로 전환
    6. 성공 시 CLOSED로 복구
    """
    print("\n" + "="*70)
    print("TEST: 위임 체인 Circuit Breaker 통합 테스트")
    print("="*70)
    
    # Circuit Breaker Manager 생성 (빠른 테스트를 위해 짧은 복구 시간)
    cb_manager = DelegationCircuitBreakerManager(
        config=CircuitBreakerConfig(
            failure_threshold=3,     # 3회 실패 시 OPEN
            recovery_timeout=2.0,    # 2초 후 복구 시도
            half_open_max_calls=1,
            success_threshold=1
        )
    )
    
    # 하위 Agent ID
    sub_agent_id = "sub_agent_test"
    cb = cb_manager.get_breaker(sub_agent_id)
    
    print(f"\n1. 초기 상태 확인")
    print(f"   - 하위 Agent: {sub_agent_id}")
    print(f"   - Circuit Breaker 상태: {cb.state.value}")
    assert cb.state == CircuitBreakerState.CLOSED
    print("   ✓ 초기 상태: CLOSED")
    
    print(f"\n2. 정상 호출 테스트")
    result = cb.call(lambda: "정상 응답")
    print(f"   - 호출 결과: {result}")
    assert result == "정상 응답"
    print("   ✓ 정상 호출 성공")
    
    print(f"\n3. 연속 실패로 OPEN 상태 전환 (3회)")
    for i in range(3):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception(f"의도적 실패 {i+1}")))
        except Exception:
            pass
    
    stats = cb.stats
    print(f"   - 연속 실패 횟수: {stats.failure_count}")
    print(f"   - Circuit Breaker 상태: {cb.state.value}")
    assert cb.state == CircuitBreakerState.OPEN
    print("   ✓ OPEN 상태 전환 확인")
    
    print(f"\n4. OPEN 상태에서 fallback 테스트")
    fallback_msg = "⚠️ 현재 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요."
    result = cb.call(
        lambda: "원래 응답",
        fallback=lambda: fallback_msg
    )
    print(f"   - 결과: {result}")
    assert result == fallback_msg
    print("   ✓ OPEN 상태에서 바로 fallback 반환 (빠른 실패)")
    
    # 통계 확인
    stats = cb.stats
    print(f"\n   [통계 정보]")
    print(f"   - 총 호출: {stats.total_calls}")
    print(f"   - 총 성공: {stats.total_successes}")
    print(f"   - 총 실패: {stats.total_failures}")
    print(f"   - 총 거부: {stats.total_rejections}")
    
    print(f"\n5. 복구 시간 대기 (2초)")
    time.sleep(2.1)
    
    # 상태 확인 시 HALF_OPEN으로 전환
    _ = cb.state
    print(f"   - Circuit Breaker 상태: {cb.state.value}")
    assert cb.state == CircuitBreakerState.HALF_OPEN
    print("   ✓ HALF_OPEN 상태로 복구 시도")
    
    print(f"\n6. HALF_OPEN에서 성공 시 CLOSED 복구")
    result = cb.call(lambda: "복구 후 정상 응답")
    print(f"   - 호출 결과: {result}")
    print(f"   - Circuit Breaker 상태: {cb.state.value}")
    assert result == "복구 후 정상 응답"
    assert cb.state == CircuitBreakerState.CLOSED
    print("   ✓ CLOSED로 복구 완료")
    
    print("\n" + "="*70)
    print("✅ 통합 테스트 완료")
    print("="*70)


def test_multiple_sub_agents():
    """
    여러 하위 Agent에 대한 Circuit Breaker 테스트
    """
    print("\n" + "="*70)
    print("TEST: 다중 하위 Agent Circuit Breaker 테스트")
    print("="*70)
    
    cb_manager = DelegationCircuitBreakerManager(
        config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0)
    )
    
    sub_agents = ["agent_hr", "agent_tech", "agent_finance"]
    
    print("\n1. 각 하위 Agent별 Circuit Breaker 생성")
    for agent_id in sub_agents:
        cb = cb_manager.get_breaker(agent_id)
        print(f"   - {agent_id}: state={cb.state.value}")
    
    print("\n2. 특정 Agent만 실패 시나리오")
    cb_hr = cb_manager.get_breaker("agent_hr")
    
    # agent_hr만 실패
    for i in range(3):
        try:
            cb_hr.call(lambda: (_ for _ in ()).throw(Exception("DB 연결 실패")))
        except Exception:
            pass
    
    print(f"   - agent_hr 상태: {cb_hr.state.value}")
    assert cb_hr.state == CircuitBreakerState.OPEN
    print("   ✓ agent_hr만 OPEN 상태")
    
    # 다른 Agent는 정상
    cb_tech = cb_manager.get_breaker("agent_tech")
    result = cb_tech.call(lambda: "기술팀 응답")
    print(f"   - agent_tech 상태: {cb_tech.state.value}, 결과: {result}")
    assert cb_tech.state == CircuitBreakerState.CLOSED
    print("   ✓ agent_tech는 CLOSED 상태 유지")
    
    print("\n3. 전체 통계 조회")
    all_stats = cb_manager.get_all_stats()
    for agent_id, stats in all_stats.items():
        print(f"   - {agent_id}: {stats.state.value}, "
              f"calls={stats.total_calls}, "
              f"failures={stats.total_failures}")
    
    print("\n" + "="*70)
    print("✅ 다중 Agent 테스트 완료")
    print("="*70)


def test_delegation_fallback_message():
    """
    위임 실패 시 사용자 친화적인 메시지 테스트
    """
    print("\n" + "="*70)
    print("TEST: 위임 실패 시 Graceful Degradation 메시지 테스트")
    print("="*70)
    
    cb_manager = DelegationCircuitBreakerManager(
        config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=30.0)
    )
    
    sub_agent_id = "agent_specialist"
    cb = cb_manager.get_breaker(sub_agent_id)
    
    # OPEN 상태로 만들기
    for _ in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("Timeout")))
        except Exception:
            pass
    
    assert cb.state == CircuitBreakerState.OPEN
    
    print("\n1. OPEN 상태에서 위임 시도")
    
    # Graceful Degradation 메시지
    def graceful_fallback():
        return (
            f"⚠️ **[{sub_agent_id}] 서비스 일시 중단**\n\n"
            f"현재 '{sub_agent_id}' 서비스가 일시적으로 사용 불가능합니다.\n"
            f"(원인: 연속 실패로 인한 서비스 보호)\n\n"
            f"잠시 후 다시 시도해 주세요."
        )
    
    result = cb.call(
        lambda: (_ for _ in ()).throw(Exception("should not execute")),
        fallback=graceful_fallback
    )
    
    print(f"\n   Fallback 메시지:\n{result}")
    
    assert "서비스 일시 중단" in result
    assert "연속 실패" in result
    print("   ✓ 사용자 친화적인 fallback 메시지 확인")
    
    print("\n" + "="*70)
    print("✅ Graceful Degradation 테스트 완료")
    print("="*70)


def run_all_tests():
    """모든 통합 테스트 실행"""
    print("\n" + "="*70)
    print("CIRCUIT BREAKER INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        test_delegation_circuit_breaker,
        test_multiple_sub_agents,
        test_delegation_fallback_message,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"\n❌ {test.__name__} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"INTEGRATION TEST RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)