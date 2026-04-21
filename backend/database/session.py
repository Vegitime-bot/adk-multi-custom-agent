"""
backend/database/session.py - PostgreSQL 연결 및 세션 관리
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from backend.config import settings

# ── SQLAlchemy 엔진 설정 ───────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # 연결 끊김 방지
    pool_recycle=3600,   # 1시간마다 연결 재생성
    echo=settings.DEBUG, # DEBUG 모드에서 SQL 로깅
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
    from backend.permissions.repository import Base
    
    inspector = inspect(engine)
    
    # 스키마 존재 확인 및 생성
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS test"))
        conn.commit()
    
    # 테이블 생성
    Base.metadata.create_all(bind=engine)
