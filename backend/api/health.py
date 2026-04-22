from __future__ import annotations
"""
api/health.py - 헬스체크 엔드포인트
"""
import logging
import os
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter
from backend.config import settings
from backend.utils.logger import get_logger, get_correlation_id

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
def health_check():
    """기본 헬스체크 엔드포인트"""
    return {
        "status": "ok",
        "use_mock_db":   settings.USE_MOCK_DB,
        "use_mock_auth": settings.USE_MOCK_AUTH,
        "ingestion_url": settings.INGESTION_BASE_URL,
        "llm_base_url":  settings.LLM_BASE_URL,
    }


@router.get("/health/detailed")
def detailed_health_check() -> Dict[str, Any]:
    """상세 헬스체크 엔드포인트"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "config": {
            "use_mock_db": settings.USE_MOCK_DB,
            "use_mock_auth": settings.USE_MOCK_AUTH,
            "use_adk": settings.USE_ADK,
            "host": settings.HOST,
            "port": settings.PORT,
            "debug": settings.DEBUG,
        },
        "services": {
            "ingestion": {
                "url": settings.INGESTION_BASE_URL,
            },
            "llm": {
                "base_url": settings.LLM_BASE_URL,
                "default_model": settings.LLM_DEFAULT_MODEL,
            },
        }
    }


@router.get("/health/logging")
def logging_health_check() -> Dict[str, Any]:
    """로깅 상태 확인 엔드포인트"""
    # 현재 로깅 설정 확인
    root_logger = logging.getLogger()
    
    # 핸들러 정보 수집
    handlers_info = []
    for handler in root_logger.handlers:
        handler_info = {
            "type": type(handler).__name__,
            "level": logging.getLevelName(handler.level),
        }
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler_info["base_filename"] = handler.baseFilename
            handler_info["max_bytes"] = handler.maxBytes
            handler_info["backup_count"] = handler.backupCount
        elif isinstance(handler, logging.StreamHandler):
            handler_info["stream"] = str(handler.stream)
        handlers_info.append(handler_info)
    
    # 환경 변수
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = os.getenv("LOG_DIR", "")
    log_to_file = os.getenv("LOG_TO_FILE", "false").lower() == "true"
    
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "logging": {
            "root_level": logging.getLevelName(root_logger.level),
            "effective_level": logging.getLevelName(root_logger.getEffectiveLevel()),
            "handlers_count": len(root_logger.handlers),
            "handlers": handlers_info,
            "environment": {
                "LOG_LEVEL": log_level,
                "LOG_DIR": log_dir,
                "LOG_TO_FILE": log_to_file,
            },
            "correlation_id_example": get_correlation_id() or "not_set",
        }
    }


@router.get("/health/test-log")
def test_logging() -> Dict[str, str]:
    """로깅 테스트 엔드포인트 - 각 레벨별 로그 메시지 출력"""
    test_correlation_id = "test-12345"
    
    logger.debug("디버그 테스트 메시지", extra={
        "test": True,
        "correlation_id": test_correlation_id
    })
    logger.info("정보 테스트 메시지", extra={
        "test": True,
        "correlation_id": test_correlation_id
    })
    logger.warning("경고 테스트 메시지", extra={
        "test": True,
        "correlation_id": test_correlation_id
    })
    
    # 민감 정보 마스킹 테스트
    logger.info("API 키 테스트", extra={
        "api_key": "secret-key-12345",
        "password": "my-password",
        "normal_field": "this-should-be-visible"
    })
    
    return {
        "status": "ok",
        "message": "로그 메시지가 출력되었습니다. 로그를 확인하세요."
    }
