from __future__ import annotations
"""
backend/utils/metrics.py - Prometheus 메트릭스 수집 유틸리티

기능:
- 요청 수 카운터
- 지연 시간 히스토그램
- 에러율 측정
- 엔드포인트별 메트릭 수집
"""

import time
from contextlib import contextmanager
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Prometheus 클라이언트는 선택적 의존성
try:
    from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # 더미 클래스 정의 (prometheus-client가 설치되지 않은 경우)
    class DummyMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
    
    Counter = Histogram = Gauge = Info = DummyMetric
    
    def generate_latest(*args): return b"# Prometheus client not installed"
    CONTENT_TYPE_LATEST = "text/plain"


class MetricsCollector:
    """Prometheus 메트릭스 수집기"""
    
    def __init__(self, prefix: str = "adk_multi"):
        self.prefix = prefix
        self.enabled = PROMETHEUS_AVAILABLE
        
        if not self.enabled:
            return
        
        # 요청 카운터
        self.request_count = Counter(
            f"{prefix}_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"]
        )
        
        # 요청 지연 시간
        self.request_duration = Histogram(
            f"{prefix}_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        
        # 에러 카운터
        self.error_count = Counter(
            f"{prefix}_http_errors_total",
            "Total HTTP errors",
            ["method", "endpoint", "error_type"]
        )
        
        # 활성 요청 수
        self.active_requests = Gauge(
            f"{prefix}_active_requests",
            "Number of active HTTP requests"
        )
        
        # 애플리케이션 정보
        self.app_info = Info(
            f"{prefix}_app_info",
            "Application information"
        )
        
        # LLM 호출 메트릭스
        self.llm_request_count = Counter(
            f"{prefix}_llm_requests_total",
            "Total LLM requests",
            ["model", "status"]
        )
        
        self.llm_request_duration = Histogram(
            f"{prefix}_llm_request_duration_seconds",
            "LLM request duration in seconds",
            ["model"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        )
        
        # 검색 메트릭스
        self.search_count = Counter(
            f"{prefix}_search_requests_total",
            "Total search requests",
            ["db_id"]
        )
        
        self.search_duration = Histogram(
            f"{prefix}_search_duration_seconds",
            "Search duration in seconds",
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
        )
        
        # 세션 메트릭스
        self.active_sessions = Gauge(
            f"{prefix}_active_sessions",
            "Number of active sessions"
        )
        
        self.session_operations = Counter(
            f"{prefix}_session_operations_total",
            "Total session operations",
            ["operation", "status"]
        )
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration: float) -> None:
        """HTTP 요청 기록"""
        if not self.enabled:
            return
        
        self.request_count.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
    
    def record_error(self, method: str, endpoint: str, error_type: str) -> None:
        """에러 기록"""
        if not self.enabled:
            return
        
        self.error_count.labels(method=method, endpoint=endpoint, error_type=error_type).inc()
    
    def record_llm_call(self, model: str, duration: float, success: bool = True) -> None:
        """LLM 호출 기록"""
        if not self.enabled:
            return
        
        status = "success" if success else "error"
        self.llm_request_count.labels(model=model, status=status).inc()
        self.llm_request_duration.labels(model=model).observe(duration)
    
    def record_search(self, db_id: str, duration: float) -> None:
        """검색 작업 기록"""
        if not self.enabled:
            return
        
        self.search_count.labels(db_id=db_id).inc()
        self.search_duration.observe(duration)
    
    def record_session_operation(self, operation: str, status: str = "success") -> None:
        """세션 작업 기록"""
        if not self.enabled:
            return
        
        self.session_operations.labels(operation=operation, status=status).inc()
    
    def set_active_sessions(self, count: int) -> None:
        """활성 세션 수 설정"""
        if not self.enabled:
            return
        
        self.active_requests.set(count)
    
    def increment_active_requests(self) -> None:
        """활성 요청 수 증가"""
        if not self.enabled:
            return
        
        self.active_requests.inc()
    
    def decrement_active_requests(self) -> None:
        """활성 요청 수 감소"""
        if not self.enabled:
            return
        
        self.active_requests.dec()
    
    def set_app_info(self, version: str, environment: str) -> None:
        """애플리케이션 정보 설정"""
        if not self.enabled:
            return
        
        self.app_info.info({"version": version, "environment": environment})
    
    @contextmanager
    def time_operation(self, operation: str, labels: Optional[dict] = None):
        """작업 시간 측정 컨텍스트 매니저"""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            # 커스텀 히스토그램이 있다면 여기서 기록


# 전역 메트릭스 수집기 인스턴스
metrics = MetricsCollector()


class PrometheusMiddleware(BaseHTTPMiddleware):
    """FastAPI용 Prometheus 미들웨어"""
    
    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None):
        super().__init__(app)
        self.metrics = metrics_collector or metrics
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        self.metrics.increment_active_requests()
        
        try:
            response = await call_next(request)
            
            duration = time.time() - start_time
            method = request.method
            endpoint = request.url.path
            status_code = response.status_code
            
            self.metrics.record_request(method, endpoint, status_code, duration)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            method = request.method
            endpoint = request.url.path
            error_type = type(e).__name__
            
            self.metrics.record_error(method, endpoint, error_type)
            
            raise
        finally:
            self.metrics.decrement_active_requests()


def setup_metrics(app, metrics_path: str = "/metrics") -> None:
    """
    FastAPI 앱에 Prometheus 메트릭스 엔드포인트 설정
    
    Args:
        app: FastAPI 애플리케이션 인스턴스
        metrics_path: 메트릭스 엔드포인트 경로
    """
    if not PROMETHEUS_AVAILABLE:
        @app.get(metrics_path)
        async def metrics_not_available():
            return Response(
                content="# Prometheus client not installed. Run: pip install prometheus-client",
                media_type="text/plain"
            )
        return
    
    @app.get(metrics_path)
    async def prometheus_metrics():
        """Prometheus 메트릭스 엔드포인트"""
        from fastapi.responses import Response as FastAPIResponse
        
        return FastAPIResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )


# 데코레이터 함수들
def timed(metric_name: str, labels: Optional[dict] = None):
    """함수 실행 시간을 측정하는 데코레이터"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                # 메트릭 기록 로직
        return wrapper
    return decorator


def count_requests(func: Callable) -> Callable:
    """함수 호출 횟수를 카운트하는 데코레이터"""
    def wrapper(*args, **kwargs):
        # 메트릭 기록 로직
        return func(*args, **kwargs)
    return wrapper


__all__ = [
    'MetricsCollector',
    'PrometheusMiddleware',
    'setup_metrics',
    'metrics',
    'PROMETHEUS_AVAILABLE',
]
