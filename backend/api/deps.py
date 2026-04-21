"""
backend/api/deps.py - 공통 의존성 주입
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from backend.managers.chatbot_manager import ChatbotManager
from backend.managers.memory_manager import MemoryManager
from backend.managers.session_manager import SessionManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.database.session import get_db_session


def get_chatbot_manager(request: Request) -> ChatbotManager:
    return request.app.state.chatbot_manager


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def get_memory_manager(request: Request) -> MemoryManager:
    return request.app.state.memory_manager


def get_ingestion_client(request: Request) -> IngestionClient:
    return request.app.state.ingestion_client


def get_db() -> Session:
    """FastAPI Depends용 DB 세션"""
    return get_db_session()
