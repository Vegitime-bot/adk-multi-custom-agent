"""
backend/utils - 유틸리티 모듈

이 패키지는 애플리케이션 전반에서 사용되는 유틸리티 기능을 제공합니다.

주요 모듈:
    - logger: 구조화된 JSON 로깅, Correlation ID 관리, 요청/응답 시간 측정
    - metrics: Prometheus 메트릭스 수집, 요청/응답 모니터링
"""

from backend.utils.logger import (
    StructuredLogger,
    get_logger,
    set_correlation_id,
    get_correlation_id,
    clear_correlation_id,
    LogContext,
    RequestTimer,
    log_execution_time,
    configure_logging,
    mask_sensitive_data,
    mask_dict_sensitive,
)

from backend.utils.metrics import (
    MetricsCollector,
    PrometheusMiddleware,
    setup_metrics,
    metrics,
    PROMETHEUS_AVAILABLE,
)

__all__ = [
    # Logger
    'StructuredLogger',
    'get_logger',
    'set_correlation_id',
    'get_correlation_id',
    'clear_correlation_id',
    'LogContext',
    'RequestTimer',
    'log_execution_time',
    'configure_logging',
    'mask_sensitive_data',
    'mask_dict_sensitive',
    # Metrics
    'MetricsCollector',
    'PrometheusMiddleware',
    'setup_metrics',
    'metrics',
    'PROMETHEUS_AVAILABLE',
]
