"""
backend/database/session.py - PostgreSQL 연결 및 세션 관리
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from contextlib import contextmanager

from backend.config import settings

USE_MOCK_DB = settings.USE_MOCK_DB

# ── Base 클래스 정의 ─────────────────────────────────────────────
Base = declarative_base()

# ── SQLite / PostgreSQL 설정 ───────────────────────────────────
SQLITE_URL = "sqlite:///./chatbot.db"

engine = create_engine(
    SQLITE_URL if USE_MOCK_DB else settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if USE_MOCK_DB else {}
)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── FastAPI 의존성 주입용 ─────────────────────────────────────────
def get_db_session() -> Session:
    """
    FastAPI Depends용: 요청마다 세션 생성/종료
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 컨텍스트 매니저 (직접 사용) ────────────────────────────────────
@contextmanager
def get_db_context():
    """
    with 문으로 직접 사용: with get_db_context() as db:
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── 앱 시작 시 테이블 생성 (선택) ──────────────────────────────────
def init_tables():
    """
    개발 환경에서 테이블 자동 생성 (운영에서는 마이그레이션 권장)
    """
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    
    # PostgreSQL용 스키마 생성 (SQLite는 무시됨)
    if not USE_MOCK_DB:
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
                conn.commit()
        except Exception:
            pass  # 이미 존재하거나 SQLite면 무시
    
    # 테이블 생성 (새 모델 포함)
    from backend.models import ChatSession, Message, DelegationChain
    Base.metadata.create_all(bind=engine)
