from __future__ import annotations
"""
api/health.py - 헬스체크 엔드포인트
"""
from fastapi import APIRouter
from backend.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "use_mock_db":   settings.USE_MOCK_DB,
        "use_mock_auth": settings.USE_MOCK_AUTH,
        "ingestion_url": settings.INGESTION_BASE_URL,
        "llm_base_url":  settings.LLM_BASE_URL,
    }
