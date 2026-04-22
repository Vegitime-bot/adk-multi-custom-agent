from __future__ import annotations
"""
backend/utils/logger.py - 구조화된 JSON 로깅 유틸리티

기능:
- JSON 형식 구조화된 로깅
- Correlation ID 지원 (요청 추적)
- 요청/응답 시간 측정
- 민감 정보 마스킹 (API 키, 비밀번호 등)
- 로그 레벨별 필터링 (DEBUG/INFO/WARNING/ERROR)
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Correlation ID 컨텍스트 변수
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')

# 민감 정보 마스킹 패턴
SENSITIVE_PATTERNS = [
    (re.compile(r'(api[_-]?key[:\s]*)([^\s,;]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'(password[:\s]*)([^\s,;]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'(secret[:\s]*)([^\s,;]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'(token[:\s]*)([^\s,;]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'(bearer\s+)([^\s,;]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'([\w-]+[_-]?id[:\s]*)([a-zA-Z0-9-]{36})', re.IGNORECASE), r'\1***UUID***'),
]


def mask_sensitive_data(text: str) -> str:
    """텍스트에서 민감 정보를 마스킹합니다."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def mask_dict_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """딕셔너리에서 민감 정보를 마스킹합니다."""
    if not isinstance(data, dict):
        return data
    
    result = {}
    sensitive_keys = {'password', 'secret', 'api_key', 'token', 'access_token', 
                      'refresh_token', 'auth', 'authorization', 'key'}
    
    for key, value in data.items():
        key_lower = key.lower()
        if any(sk in key_lower for sk in sensitive_keys):
            result[key] = '***MASKED***'
        elif isinstance(value, dict):
            result[key] = mask_dict_sensitive(value)
        elif isinstance(value, str):
            result[key] = mask_sensitive_data(value)
        else:
            result[key] = value
    return result


class JSONFormatter(logging.Formatter):
    """JSON 형식으로 로그를 포맷팅합니다."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': mask_sensitive_data(record.getMessage()),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Correlation ID 추가
        corr_id = correlation_id_var.get()
        if corr_id:
            log_data['correlation_id'] = corr_id
        
        # 추가 필드 처리
        if hasattr(record, 'extra_data') and record.extra_data:
            log_data.update(mask_dict_sensitive(record.extra_data))
        
        # 예외 정보
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class StructuredLogger:
    """
    구조화된 로깅을 제공하는 래퍼 클래스
    
    사용 예시:
        from backend.utils.logger import get_logger
        
        logger = get_logger(__name__)
        logger.info("메시지", extra={"user_id": "123"})
        logger.error("에러 발생", extra={"error_code": 500})
    """
    
    def __init__(self, name: str, level: Optional[int] = None):
        self._logger = logging.getLogger(name)
        self._logger.propagate = False
        
        # 레벨 설정
        if level is not None:
            self._logger.setLevel(level)
        else:
            env_level = os.getenv('LOG_LEVEL', 'INFO').upper()
            self._logger.setLevel(getattr(logging, env_level, logging.INFO))
        
        # 핸들러 중복 추가 방지
        if not self._logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """로그 핸들러 설정"""
        # stdout 핸들러 (JSON 형식)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(JSONFormatter())
        self._logger.addHandler(stdout_handler)
        
        # 파일 핸들러 (선택적)
        log_dir = Path(os.getenv('LOG_DIR', 'logs'))
        if log_dir.exists() or os.getenv('LOG_TO_FILE'):
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / 'app.log',
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(JSONFormatter())
            self._logger.addHandler(file_handler)
    
    def _log(self, level: int, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """내부 로깅 메서드"""
        if extra:
            extra_data = mask_dict_sensitive(extra)
        else:
            extra_data = {}
        
        extra_attrs = {'extra_data': extra_data}
        self._logger.log(level, msg, extra=extra_attrs)
    
    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.DEBUG, msg, extra)
    
    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.INFO, msg, extra)
    
    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.WARNING, msg, extra)
    
    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.ERROR, msg, extra)
    
    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.CRITICAL, msg, extra)
    
    def exception(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """예외 정보를 포함한 에러 로깅"""
        if extra:
            extra_data = mask_dict_sensitive(extra)
        else:
            extra_data = {}
        
        extra_attrs = {'extra_data': extra_data}
        self._logger.exception(msg, extra=extra_attrs)
    
    # Alias for exception
    def log_exception(self, msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self.exception(msg, extra)


# 싱글톤 캐시
_logger_cache: Dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    """StructuredLogger 인스턴스를 가져옵니다."""
    if name not in _logger_cache:
        _logger_cache[name] = StructuredLogger(name)
    return _logger_cache[name]


def set_correlation_id(corr_id: Optional[str] = None) -> str:
    """
    Correlation ID를 설정합니다.
    
    Args:
        corr_id: 설정할 ID (None이면 자동 생성)
    
    Returns:
        설정된 Correlation ID
    """
    if corr_id is None:
        corr_id = str(uuid.uuid4())[:8]
    correlation_id_var.set(corr_id)
    return corr_id


def get_correlation_id() -> str:
    """현재 Correlation ID를 반환합니다."""
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Correlation ID를 초기화합니다."""
    correlation_id_var.set('')


class LogContext:
    """
    Context Manager를 통한 Correlation ID 관리
    
    사용 예시:
        with LogContext() as corr_id:
            logger.info("요청 시작", extra={"corr_id": corr_id})
            # ... 작업 수행 ...
    """
    
    def __init__(self, corr_id: Optional[str] = None):
        self.corr_id = corr_id or str(uuid.uuid4())[:8]
        self._token = None
    
    def __enter__(self) -> str:
        self._token = correlation_id_var.set(self.corr_id)
        return self.corr_id
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            correlation_id_var.reset(self._token)


class RequestTimer:
    """
    요청/응답 시간을 측정하는 컨텍스트 매니저
    
    사용 예시:
        with RequestTimer("api_call") as timer:
            result = api.call()
        # 종료 시 자동으로 소요 시간 로깅
    """
    
    def __init__(self, operation: str, logger: Optional[StructuredLogger] = None, 
                 log_level: str = "info"):
        self.operation = operation
        self.logger = logger or get_logger(__name__)
        self.log_level = log_level
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self) -> 'RequestTimer':
        self.start_time = time.time()
        self.logger.debug(f"[{self.operation}] 시작", extra={
            'operation': self.operation,
            'event': 'start'
        })
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        extra = {
            'operation': self.operation,
            'duration_ms': round(duration_ms, 2),
            'event': 'end'
        }
        
        if exc_type:
            extra['error'] = str(exc_val)
            extra['error_type'] = exc_type.__name__
            self.logger.error(f"[{self.operation}] 실패 (소요시간: {duration_ms:.2f}ms)", extra=extra)
        else:
            log_func = getattr(self.logger, self.log_level, self.logger.info)
            log_func(f"[{self.operation}] 완료 (소요시간: {duration_ms:.2f}ms)", extra=extra)
    
    @property
    def elapsed_ms(self) -> float:
        """경과 시간(ms)을 반환합니다."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000


def log_execution_time(logger: Optional[StructuredLogger] = None, 
                       operation: Optional[str] = None):
    """
    함수 실행 시간을 측정하는 데코레이터
    
    사용 예시:
        @log_execution_time()
        def my_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        log = logger or get_logger(func.__module__)
        op_name = operation or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            with RequestTimer(op_name, log):
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


def configure_logging(
    level: Union[str, int] = "INFO",
    log_dir: Optional[Union[str, Path]] = None,
    json_format: bool = True
) -> None:
    """
    전체 애플리케이션 로깅을 설정합니다.
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 로그 파일 저장 디렉토리 (None이면 파일 로깅 비활성화)
        json_format: JSON 형식 사용 여부
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 기존 핸들러 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # stdout 핸들러
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    
    if json_format:
        stdout_handler.setFormatter(JSONFormatter())
    else:
        stdout_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
    
    root_logger.addHandler(stdout_handler)
    
    # 파일 핸들러
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / 'app.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        
        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
        
        root_logger.addHandler(file_handler)


# Convenience functions for module-level imports
__all__ = [
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
]
