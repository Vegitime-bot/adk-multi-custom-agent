"""
test_circuit_breaker.py - Circuit Breaker 테스트

실행 방법:
    python tests/test_circuit_breaker.py
"""
import sys
import time
import threading
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitBreakerOpenError,
    DelegationCircuitBreakerManager,
    circuit_breaker_protected,
)


def test_circuit_breaker_basic():
    """기본 Circuit Breaker 테스트"""
    print("\n" + "="*60)
    print("TEST 1: 기본 Circuit Breaker 동작 테스트")
    print("="*60)
    
    # 새로운 Circuit Breaker 생성 (싱글톤 패턴이므로 고유 이름 사용)
    cb = CircuitBreaker(
        name="test_basic_" + str(int(time.time())),
        config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0)
    )
    
    # 초기 상태 확인
    assert cb.state == CircuitBreakerState.CLOSED, "초기 상태는 CLOSED여야 함"
    print(f"✓ 초기 상태: {cb.state.value}")
    
    # 성공 호출
    result = cb.call(lambda: "success")
    assert result == "success", "성공 결과 반환"
    print(f"✓ 성공 호출 결과: {result}")
    
    # 연속 실패로 OPEN 상태 전환
    print("\n- 연속 3회 실패로 OPEN 상태 전환 테스트")
    for i in range(3):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception(f"fail_{i}")))
        except Exception:
            pass
    
    assert cb.state == CircuitBreakerState.OPEN, "3회 실패 후 OPEN 상태여야 함"
    print(f"✓ 3회 실패 후 상태: {cb.state.value}")
    
    # OPEN 상태에서 호출 시 예외 발생 (fallback 없음)
    try:
        cb.call(lambda: "should_not_execute")
        assert False, "OPEN 상태에서 예외가 발생해야 함"
    except CircuitBreakerOpenError as e:
        print(f"✓ OPEN 상태에서 CircuitBreakerOpenError 발생: {e.message}")
    
    # OPEN 상태에서 fallback 사용
    result = cb.call(lambda: "should_not_execute", fallback=lambda: "fallback_result")
    assert result == "fallback_result", "fallback 결과 반환"
    print(f"✓ OPEN 상태에서 fallback 결과: {result}")
    
    print("\n✅ TEST 1 PASSED")


def test_circuit_breaker_recovery():
    """복구 시간 테스트"""
    print("\n" + "="*60)
    print("TEST 2: Circuit Breaker 복구 시간 테스트")
    print("="*60)
    
    # 짧은 복구 시간 설정
    cb = CircuitBreaker(
        name="test_recovery_" + str(int(time.time())),
        config=CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=1.0,  # 1초 후 복구 시도
            half_open_max_calls=1
        )
    )
    
    # OPEN 상태로 만듦
    for i in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
    
    assert cb.state == CircuitBreakerState.OPEN, "OPEN 상태 확인"
    print(f"✓ OPEN 상태: {cb.state.value}")
    
    # 복구 대기
    print("- 1초 대기 중...")
    time.sleep(1.1)
    
    # 상태 확인 시 HALF_OPEN으로 전환
    state = cb.state
    assert state == CircuitBreakerState.HALF_OPEN, "1초 후 HALF_OPEN 상태여야 함"
    print(f"✓ 복구 후 상태: {state.value}")
    
    # HALF_OPEN에서 성공 시 CLOSED로 복구
    result = cb.call(lambda: "success")
    assert cb.state == CircuitBreakerState.CLOSED, "성공 후 CLOSED 상태"
    print(f"✓ 성공 후 상태: {cb.state.value}")
    
    print("\n✅ TEST 2 PASSED")


def test_circuit_breaker_stats():
    """통계 정보 테스트"""
    print("\n" + "="*60)
    print("TEST 3: Circuit Breaker 통계 정보 테스트")
    print("="*60)
    
    cb = CircuitBreaker(
        name="test_stats_" + str(int(time.time())),
        config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0)
    )
    
    # 여러 호출 실행
    cb.call(lambda: "success1")
    cb.call(lambda: "success2")
    
    try:
        cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
    except Exception:
        pass
    
    # 통계 확인
    stats = cb.stats
    print(f"✓ 상태: {stats.state.value}")
    print(f"✓ 총 호출: {stats.total_calls}")
    print(f"✓ 총 성공: {stats.total_successes}")
    print(f"✓ 총 실패: {stats.total_failures}")
    print(f"✓ 연속 실패: {stats.failure_count}")
    
    assert stats.total_calls == 3, "총 3회 호출"
    assert stats.total_successes == 2, "2회 성공"
    assert stats.total_failures == 1, "1회 실패"
    
    print("\n✅ TEST 3 PASSED")


def test_delegation_manager():
    """Delegation Circuit Breaker Manager 테스트"""
    print("\n" + "="*60)
    print("TEST 4: Delegation Circuit Breaker Manager 테스트")
    print("="*60)
    
    manager = DelegationCircuitBreakerManager(
        config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0)
    )
    
    # 여러 Agent용 Circuit Breaker 생성
    agent_ids = ["agent_a", "agent_b", "agent_c"]
    for agent_id in agent_ids:
        cb = manager.get_breaker(agent_id)
        assert cb is not None, f"{agent_id} Circuit Breaker 생성"
        print(f"✓ {agent_id} Circuit Breaker 생성: state={cb.state.value}")
    
    # 동일 ID로 다시 가져오기 (싱글톤)
    cb1 = manager.get_breaker("agent_a")
    cb2 = manager.get_breaker("agent_a")
    assert cb1 is cb2, "동일 ID는 동일 인스턴스 반환"
    print("✓ 동일 ID는 동일 인스턴스 반환 (싱글톤)")
    
    # 전체 통계 확인
    all_stats = manager.get_all_stats()
    print(f"✓ 전체 통계: {len(all_stats)}개 Agent")
    
    # 특정 Agent 통계
    stats = manager.get_stats("agent_a")
    assert stats is not None, "agent_a 통계 존재"
    print(f"✓ agent_a 통계: state={stats.state.value}")
    
    print("\n✅ TEST 4 PASSED")


def test_circuit_breaker_decorator():
    """데코레이터 테스트"""
    print("\n" + "="*60)
    print("TEST 5: Circuit Breaker 데코레이터 테스트")
    print("="*60)
    
    cb = CircuitBreaker(
        name="test_decorator_" + str(int(time.time())),
        config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=30.0)
    )
    
    call_count = 0
    fallback_count = 0
    should_fail = False
    
    def fallback_func():
        nonlocal fallback_count
        fallback_count += 1
        return "fallback_result"
    
    @circuit_breaker_protected(cb, fallback=fallback_func)
    def protected_function():
        nonlocal call_count, should_fail
        call_count += 1
        if should_fail:
            raise Exception("intentional failure")
        return "success"
    
    # 정상 호출
    result = protected_function()
    assert result == "success"
    print(f"✓ 정상 호출: {result}")
    
    # 연속 실패로 OPEN 상태 (fallback도 호출되므로 fallback_count 증가)
    should_fail = True
    for _ in range(2):
        try:
            protected_function()
        except Exception:
            pass
    
    # OPEN 상태에서 fallback 실행
    should_fail = False
    result = protected_function()
    assert result == "fallback_result", "OPEN 상태에서 fallback 결과"
    # 2번의 실패에서 각각 fallback 호출되고, 1번 OPEN 상태에서 fallback = 총 3회
    assert fallback_count >= 1, "fallback이 호출되어야 함"
    print(f"✓ OPEN 상태에서 fallback: {result} (fallback 호출 {fallback_count}회)")
    
    print("\n✅ TEST 5 PASSED")


def test_graceful_degradation():
    """Graceful Degradation 테스트"""
    print("\n" + "="*60)
    print("TEST 6: Graceful Degradation 메시지 테스트")
    print("="*60)
    
    cb = CircuitBreaker(
        name="test_graceful_" + str(int(time.time())),
        config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=30.0)
    )
    
    # 실패로 OPEN 상태
    try:
        cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
    except Exception:
        pass
    
    assert cb.state == CircuitBreakerState.OPEN
    
    # 사용자 친화적인 fallback 메시지
    user_friendly_msg = "⚠️ 현재 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해 주세요."
    result = cb.call(lambda: "original", fallback=lambda: user_friendly_msg)
    
    assert user_friendly_msg in result, "사용자 친화적인 메시지 반환"
    print(f"✓ Fallback 메시지: {result}")
    
    print("\n✅ TEST 6 PASSED")


def test_thread_safety():
    """스레드 안전성 테스트"""
    print("\n" + "="*60)
    print("TEST 7: 스레드 안전성 테스트")
    print("="*60)
    
    cb = CircuitBreaker(
        name="test_thread_" + str(int(time.time())),
        config=CircuitBreakerConfig(failure_threshold=10, recovery_timeout=30.0)
    )
    
    success_count = 0
    error_count = 0
    lock = threading.Lock()
    
    def worker():
        nonlocal success_count, error_count
        try:
            result = cb.call(lambda: "success")
            with lock:
                if result == "success":
                    success_count += 1
        except Exception:
            with lock:
                error_count += 1
    
    threads = []
    for _ in range(20):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    print(f"✓ 동시 호출: 성공 {success_count}회, 실패 {error_count}회")
    assert success_count == 20, "모든 호출 성공"
    assert error_count == 0, "실패 없음"
    
    print("\n✅ TEST 7 PASSED")


def test_half_open_failure():
    """HALF_OPEN 상태에서 실패 테스트"""
    print("\n" + "="*60)
    print("TEST 8: HALF_OPEN 상태에서 실패 시 다시 OPEN 테스트")
    print("="*60)
    
    cb = CircuitBreaker(
        name="test_half_fail_" + str(int(time.time())),
        config=CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.5,  # 빠른 복구
            half_open_max_calls=1
        )
    )
    
    # OPEN 상태로
    for _ in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
    
    assert cb.state == CircuitBreakerState.OPEN
    print(f"✓ OPEN 상태")
    
    # 복구 대기
    time.sleep(0.6)
    
    # HALF_OPEN 확인
    _ = cb.state  # 상태 확인 메서드 호출
    assert cb.state == CircuitBreakerState.HALF_OPEN
    print(f"✓ HALF_OPEN 상태 (복구 시도)")
    
    # HALF_OPEN에서 실패 시 다시 OPEN
    try:
        cb.call(lambda: (_ for _ in ()).throw(Exception("fail_in_half_open")))
    except Exception:
        pass
    
    assert cb.state == CircuitBreakerState.OPEN, "HALF_OPEN에서 실패 시 다시 OPEN"
    print(f"✓ HALF_OPEN 실패 후 다시 OPEN 상태")
    
    print("\n✅ TEST 8 PASSED")


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "="*70)
    print("CIRCUIT BREAKER COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    tests = [
        test_circuit_breaker_basic,
        test_circuit_breaker_recovery,
        test_circuit_breaker_stats,
        test_delegation_manager,
        test_circuit_breaker_decorator,
        test_graceful_degradation,
        test_thread_safety,
        test_half_open_failure,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {test.__name__} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)