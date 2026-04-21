from __future__ import annotations
"""
users/repository.py - UserRepository 인터페이스 + Mock/PG 구현체
USE_MOCK_DB=true  → MockUserRepository (개발/테스트)
USE_MOCK_DB=false → PGUserRepository   (운영)
"""
from abc import ABC, abstractmethod

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.users.models import Base, User


# ── 글로벌 DB 엔진/세션 팩토리 (지연 초기화) ───────────────────────
_engine = None
_session_factory = None


def _get_or_create_engine(database_url: str):
    """글로벌 엔진 생성 (싱글턴)"""
    global _engine
    if _engine is None:
        _engine = create_engine(database_url, pool_pre_ping=True)
        Base.metadata.create_all(_engine)
    return _engine


def _get_session_factory(database_url: str):
    """글로벌 세션 팩토리 생성 (싱글턴)"""
    global _session_factory
    if _session_factory is None:
        engine = _get_or_create_engine(database_url)
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _session_factory


def get_db_session(database_url: str):
    """DB 세션을 생성하여 반환 (with문에서 사용)"""
    factory = _get_session_factory(database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()


# ── 인터페이스 ─────────────────────────────────────────────────────
class UserRepository(ABC):
    @abstractmethod
    def get_user_by_knox_id(self, knox_id: str) -> dict | None:
        pass

    @abstractmethod
    def get_all_users(self) -> list[dict]:
        pass


# ── Mock 구현체 ────────────────────────────────────────────────────
MOCK_USERS: list[dict] = [
    {"knox_id": "jyd1234", "name": "장영동", "team": "AI팀",  "eng_name": "Youngdong Jang"},
    {"knox_id": "kim5678", "name": "김철수", "team": "개발팀", "eng_name": "Chulsoo Kim"},
]


class MockUserRepository(UserRepository):
    def get_user_by_knox_id(self, knox_id: str) -> dict | None:
        return next((u for u in MOCK_USERS if u["knox_id"] == knox_id), None)

    def get_all_users(self) -> list[dict]:
        return MOCK_USERS


# ── PostgreSQL 구현체 ──────────────────────────────────────────────
class PGUserRepository(UserRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_knox_id(self, knox_id: str) -> dict | None:
        try:
            user = self.db.query(User).filter_by(knox_id=knox_id).first()
            return user.to_dict() if user else None
        except Exception as e:
            print(f"[PGUserRepository] DB 조회 오류: {e}")
            return None

    def get_all_users(self) -> list[dict]:
        try:
            return [u.to_dict() for u in self.db.query(User).all()]
        except Exception as e:
            print(f"[PGUserRepository] DB 조회 오류: {e}")
            return []


# ── 팩토리 함수 ────────────────────────────────────────────────────
_db_url_cache = None


def get_user_repository(use_mock: bool = True, db: Session | None = None, database_url: str | None = None) -> UserRepository:
    """
    UserRepository 팩토리
    
    사용법:
    - Mock: get_user_repository(use_mock=True)
    - PG (세션 직접 전달): get_user_repository(use_mock=False, db=session)
    - PG (자동 연결): get_user_repository(use_mock=False, database_url=url)
    """
    if use_mock:
        return MockUserRepository()
    
    # db 세션이 직접 전달된 경우
    if db is not None:
        return PGUserRepository(db)
    
    # database_url로 자동 연결
    if database_url is not None:
        factory = _get_session_factory(database_url)
        session = factory()
        return PGUserRepository(session)
    
    raise ValueError("PGUserRepository requires either db=Session or database_url=...")


def create_pg_session_factory(database_url: str):
    """운영 환경에서 사용하는 SQLAlchemy 세션 팩토리를 반환한다."""
    return _get_session_factory(database_url)
