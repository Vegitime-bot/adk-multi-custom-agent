"""
circuit_breaker.py - Circuit Breaker 패턴 구현

위임 체인 실패 시 Circuit Breaker 및 Graceful Degradation 제공
- CLOSED: 정상 상태 (호출 허용)
- OPEN: 실패 상태 (호출 차단, 빠른 실패)
- HALF_OPEN: 복구 시도 상태 (제한적 호출 허용)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional, TypeVar, Generic
from functools import wraps

T = TypeVar('T')


class CircuitBreakerState(Enum):
    """Circuit Breaker 상태"""
    CLOSED = "closed"       # 정상 상태 - 모든 호출 허용
    OPEN = "open"          # 차단 상태 - 모든 호출 거부
    HALF_OPEN = "half_open"  # 복구 시도 상태 - 제한적 호출 허용


@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker 설정"""
    failure_threshold: int = None  # 설정에서 동적 로드
    recovery_timeout: float = None  # 설정에서 동적 로드
    half_open_max_calls: int = 1   # HALF_OPEN 상태에서 허용할 최대 호출 수
    success_threshold: int = 1      # CLOSED로 복구될 성공 횟수

    def __post_init__(self):
        """설정에서 기본값 로드"""
        if self.failure_threshold is None or self.recovery_timeout is None:
            try:
                from config import settings
                if self.failure_threshold is None:
                    self.failure_threshold = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
                if self.recovery_timeout is None:
                    self.recovery_timeout = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
            except (ImportError, AttributeError):
                # 폴백 기본값
                if self.failure_threshold is None:
                    self.failure_threshold = 3
                if self.recovery_timeout is None:
                    self.recovery_timeout = 30.0


@dataclass
class CircuitBreakerStats:
    """Circuit Breaker 통계"""
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejections: int = 0


class CircuitBreakerOpenError(Exception):
    """Circuit Breaker가 OPEN 상태일 때 발생하는 예외"""
    def __init__(self, name: str, message: str = ""):
        self.name = name
        self.message = message or f"CircuitBreaker '{name}' is OPEN"
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit Breaker 패턴 구현
    
    위임 체인에서 하위 Agent 호출 실패 시 자동으로 상태를 관리하고
    Graceful Degradation을 제공합니다.
    
    사용 예시:
        cb = CircuitBreaker("sub_agent_delegation")
        
        # 동기 호출
        result = cb.call(lambda: sub_agent.execute(message))
        
        # 데코레이터 사용
        @circuit_breaker_protected(cb)
        def delegate_to_sub(message):
            return sub_agent.process(message)
    """
    
    _instances: dict[str, 'CircuitBreaker'] = {}
    _lock = threading.Lock()
    
    def __new__(cls, name: str, config: Optional[CircuitBreakerConfig] = None):
        """싱글톤 패턴 - 동일 이름의 CircuitBreaker는 하나만 생성"""
        with cls._lock:
            if name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[name] = instance
            return cls._instances[name]
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        CircuitBreaker 초기화
        
        Args:
            name: CircuitBreaker 식별자
            config: CircuitBreaker 설정 (None이면 기본값 사용)
        """
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.time()
        self._lock = threading.RLock()
        
        # 통계
        self._stats = CircuitBreakerStats()
    
    @property
    def state(self) -> CircuitBreakerState:
        """현재 상태 반환"""
        with self._lock:
            self._check_and_transition()
            return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """통계 정보 반환"""
        with self._lock:
            stats = CircuitBreakerStats(
                state=self._state,
                failure_count=self._failure_count,
                success_count=self._success_count,
                last_failure_time=self._last_failure_time,
                last_state_change=self._last_state_change,
                total_calls=self._stats.total_calls,
                total_failures=self._stats.total_failures,
                total_successes=self._stats.total_successes,
                total_rejections=self._stats.total_rejections,
            )
            return stats
    
    def _check_and_transition(self) -> None:
        """상태 확인 및 전환"""
        if self._state == CircuitBreakerState.OPEN:
            # OPEN -> HALF_OPEN 체크
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.recovery_timeout:
                    self._transition_to(CircuitBreakerState.HALF_OPEN)
                    self._half_open_calls = 0
    
    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """상태 전환"""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()
        
        if new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitBreakerState.OPEN:
            self._last_failure_time = time.time()
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
    
    def can_execute(self) -> bool:
        """실행 가능 여부 확인"""
        with self._lock:
            self._check_and_transition()
            
            if self._state == CircuitBreakerState.CLOSED:
                return True
            elif self._state == CircuitBreakerState.OPEN:
                self._stats.total_rejections += 1
                return False
            elif self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    return True
                self._stats.total_rejections += 1
                return False
            
            return True
    
    def call(self, func: Callable[[], T], fallback: Optional[Callable[[], T]] = None) -> T:
        """
        Circuit Breaker로 보호된 함수 호출
        
        Args:
            func: 실행할 함수
            fallback: 실패 시 대체 함수 (None이면 예외 발생)
            
        Returns:
            함수 실행 결과
            
        Raises:
            CircuitBreakerOpenError: Circuit Breaker가 OPEN 상태이고 fallback이 없을 때
            Exception: func 실행 중 발생한 예외
        """
        if not self.can_execute():
            if fallback:
                return fallback()
            raise CircuitBreakerOpenError(self.name)
        
        try:
            self._stats.total_calls += 1
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1
            
            result = func()
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            if fallback:
                return fallback()
            raise
    
    async def call_async(self, func: Callable[[], Any], fallback: Optional[Callable[[], Any]] = None) -> Any:
        """
        Circuit Breaker로 보호된 비동기 함수 호출
        
        Args:
            func: 실행할 비동기 함수
            fallback: 실패 시 대체 함수
            
        Returns:
            함수 실행 결과
        """
        if not self.can_execute():
            if fallback:
                return await fallback() if callable(fallback) else fallback
            raise CircuitBreakerOpenError(self.name)
        
        try:
            self._stats.total_calls += 1
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1
            
            result = await func()
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            if fallback:
                return await fallback() if callable(fallback) else fallback
            raise
    
    def _on_success(self) -> None:
        """성공 처리"""
        with self._lock:
            self._stats.total_successes += 1
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitBreakerState.CLOSED)
            else:
                self._failure_count = 0
    
    def _on_failure(self) -> None:
        """실패 처리"""
        with self._lock:
            self._stats.total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                # HALF_OPEN에서 실패하면 바로 OPEN
                self._transition_to(CircuitBreakerState.OPEN)
            elif self._failure_count >= self.config.failure_threshold:
                # CLOSED에서 연속 실패 임계값 도달 시 OPEN
                self._transition_to(CircuitBreakerState.OPEN)
    
    def reset(self) -> None:
        """Circuit Breaker 수동 리셋"""
        with self._lock:
            self._transition_to(CircuitBreakerState.CLOSED)
    
    def force_open(self) -> None:
        """강제로 OPEN 상태로 전환"""
        with self._lock:
            self._transition_to(CircuitBreakerState.OPEN)
    
    def __repr__(self) -> str:
        return f"CircuitBreaker(name='{self.name}', state={self.state.value}, failures={self._failure_count})"


def circuit_breaker_protected(
    cb: CircuitBreaker,
    fallback: Optional[Callable] = None,
    fallback_message: Optional[str] = None
):
    """
    Circuit Breaker 데코레이터
    
    Args:
        cb: CircuitBreaker 인스턴스
        fallback: 실패 시 대체 함수 (인자 없이 호출됨)
        fallback_message: 사용자 친화적인 fallback 메시지
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            def _fallback():
                if fallback:
                    return fallback()
                if fallback_message:
                    return fallback_message
                return f"⚠️ 일시적으로 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요. (CircuitBreaker: {cb.name})"
            
            return cb.call(lambda: func(*args, **kwargs), _fallback)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            async def _fallback():
                if fallback:
                    result = fallback()
                    if hasattr(result, '__await__'):
                        return await result
                    return result
                if fallback_message:
                    return fallback_message
                return f"⚠️ 일시적으로 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요. (CircuitBreaker: {cb.name})"
            
            return await cb.call_async(lambda: func(*args, **kwargs), _fallback)
        
        # 동기/비동기 구분
        if hasattr(func, '__await__'):
            return async_wrapper
        return wrapper
    
    return decorator


class DelegationCircuitBreakerManager:
    """
    위임 체인용 Circuit Breaker 관리자
    
    각 하위 Agent별로 Circuit Breaker를 관리하고
    Graceful Degradation을 제공합니다.
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._breakers: dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, agent_id: str) -> CircuitBreaker:
        """Agent별 Circuit Breaker 가져오기 (없으면 생성)"""
        if agent_id not in self._breakers:
            self._breakers[agent_id] = CircuitBreaker(
                name=f"delegation_{agent_id}",
                config=self.config
            )
        return self._breakers[agent_id]
    
    def get_stats(self, agent_id: str) -> Optional[CircuitBreakerStats]:
        """Agent별 통계 가져오기"""
        if agent_id in self._breakers:
            return self._breakers[agent_id].stats
        return None
    
    def reset_all(self) -> None:
        """모든 Circuit Breaker 리셋"""
        for cb in self._breakers.values():
            cb.reset()
    
    def get_all_stats(self) -> dict[str, CircuitBreakerStats]:
        """모든 Circuit Breaker 통계 가져오기"""
        return {agent_id: cb.stats for agent_id, cb in self._breakers.items()}