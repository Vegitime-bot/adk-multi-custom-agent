"""
backend/permissions/repository.py - Permission Repository
사용자-챗봇 권한 관리 (PostgreSQL / Mock)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from backend.config import settings

Base = declarative_base()


class UserChatbotAccess(Base):
    """사용자-챗봇 접근 권한 테이블"""
    __tablename__ = 'user_chatbot_access'
    __table_args__ = (
        UniqueConstraint('knox_id', 'chatbot_id', name='unique_user_chatbot'),
        {'schema': 'test'}
    )

    id = Column(Integer, primary_key=True)
    knox_id = Column(String(50), nullable=True)
    chatbot_id = Column(String(50), nullable=True)
    can_access = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knox_id": self.knox_id,
            "chatbot_id": self.chatbot_id,
            "can_access": self.can_access,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserDbAccess(Base):
    """사용자-DB 접근 권한 테이블"""
    __tablename__ = 'user_db_access'
    __table_args__ = (
        UniqueConstraint('knox_id', 'db_id', name='unique_user_db'),
        {'schema': 'test'}
    )

    id = Column(Integer, primary_key=True)
    knox_id = Column(String(50), nullable=True)
    db_id = Column(String(50), nullable=True)
    can_access = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knox_id": self.knox_id,
            "db_id": self.db_id,
            "can_access": self.can_access,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 인터페이스 ─────────────────────────────────────────────────────
class PermissionRepository(ABC):
    @abstractmethod
    def get_user_permissions(self, knox_id: str) -> List[dict]:
        """사용자의 모든 챗봇 권한 조회"""
        pass

    @abstractmethod
    def check_access(self, knox_id: str, chatbot_id: str) -> bool:
        """특정 챗봇 접근 권한 확인"""
        pass

    @abstractmethod
    def grant_access(self, knox_id: str, chatbot_id: str, can_access: bool = True) -> bool:
        """권한 부여/수정"""
        pass

    @abstractmethod
    def revoke_access(self, knox_id: str, chatbot_id: str) -> bool:
        """권한 철회 (삭제)"""
        pass

    @abstractmethod
    def get_chatbot_users(self, chatbot_id: str) -> List[dict]:
        """특정 챗봇에 접근 가능한 사용자 목록"""
        pass

    @abstractmethod
    def get_all_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        """전체 권한 목록 (페이징)"""
        pass

    # DB 권한 메서드
    @abstractmethod
    def get_user_db_permissions(self, knox_id: str) -> List[dict]:
        """사용자의 DB 권한 목록 조회"""
        pass

    @abstractmethod
    def grant_db_access(self, knox_id: str, db_id: str, can_access: bool = True) -> bool:
        """DB 권한 부여/수정"""
        pass

    @abstractmethod
    def revoke_db_access(self, knox_id: str, db_id: str) -> bool:
        """DB 권한 철회"""
        pass

    @abstractmethod
    def get_all_db_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        """전체 DB 권한 목록"""
        pass


# ── Mock 구현체 ────────────────────────────────────────────────────
class MockPermissionRepository(PermissionRepository):
    """개발/테스트용 Mock 권한 저장소"""

    def __init__(self):
        # 메모리 내 권한 데이터
        self._permissions: dict[tuple[str, str], dict] = {}
        self._init_mock_data()

    def _init_mock_data(self):
        """초기 Mock 데이터 로드"""
        mock_data = [
            # user-001: 관리자 (전체 접근)
            ("user-001", "chatbot-a", True),
            ("user-001", "chatbot-b", True),
            ("user-001", "chatbot-c", True),
            ("user-001", "chatbot-d", True),
            ("user-001", "chatbot-hr", True),
            ("user-001", "chatbot-hr-policy", True),
            ("user-001", "chatbot-hr-benefit", True),
            ("user-001", "chatbot-tech", True),
            ("user-001", "chatbot-tech-backend", True),
            ("user-001", "chatbot-tech-frontend", True),
            ("user-001", "chatbot-tech-devops", True),
            ("user-001", "chatbot-rtl-verilog", True),
            ("user-001", "chatbot-rtl-synthesis", True),
            # user-002: 인사팀
            ("user-002", "chatbot-hr", True),
            ("user-002", "chatbot-hr-policy", True),
            ("user-002", "chatbot-hr-benefit", True),
            ("user-002", "chatbot-a", True),
            ("user-002", "chatbot-b", False),
            ("user-002", "chatbot-tech", False),
            ("user-002", "chatbot-tech-backend", False),
            # user-003: 기술개발팀
            ("user-003", "chatbot-tech", True),
            ("user-003", "chatbot-tech-backend", True),
            ("user-003", "chatbot-tech-frontend", True),
            ("user-003", "chatbot-tech-devops", True),
            ("user-003", "chatbot-rtl-verilog", True),
            ("user-003", "chatbot-rtl-synthesis", True),
            ("user-003", "chatbot-c", True),
            ("user-003", "chatbot-a", True),
            ("user-003", "chatbot-hr", False),
            ("user-003", "chatbot-b", False),
            # system: 시스템 계정
            ("system", "chatbot-a", True),
            ("system", "chatbot-b", True),
            ("system", "chatbot-c", True),
            ("system", "chatbot-d", True),
            ("system", "chatbot-hr", True),
            ("system", "chatbot-hr-policy", True),
            ("system", "chatbot-hr-benefit", True),
            ("system", "chatbot-tech", True),
            ("system", "chatbot-tech-backend", True),
            ("system", "chatbot-tech-frontend", True),
            ("system", "chatbot-tech-devops", True),
            ("system", "chatbot-rtl-verilog", True),
            ("system", "chatbot-rtl-synthesis", True),
            # guest: 제한된 접근
            ("guest", "chatbot-a", True),
            ("guest", "chatbot-b", False),
            ("guest", "chatbot-c", False),
            ("guest", "chatbot-hr", True),
            ("guest", "chatbot-tech", True),
        ]

        now = datetime.utcnow()
        for i, (knox_id, chatbot_id, can_access) in enumerate(mock_data, 1):
            self._permissions[(knox_id, chatbot_id)] = {
                "id": i,
                "knox_id": knox_id,
                "chatbot_id": chatbot_id,
                "can_access": can_access,
                "created_at": now.isoformat(),
            }

    def get_user_permissions(self, knox_id: str) -> List[dict]:
        return [
            p for (k, c), p in self._permissions.items()
            if k == knox_id
        ]

    def check_access(self, knox_id: str, chatbot_id: str) -> bool:
        """
        특정 챗봇 접근 권한 확인
        - 권한이 없으면 기본적으로 허용 (True)
        - 명시적으로 차단된 경우만 차단 (can_access=False)
        """
        key = (knox_id, chatbot_id)
        if key not in self._permissions:
            return True  # 기본값: 허용
        return self._permissions[key]["can_access"]

    def grant_access(self, knox_id: str, chatbot_id: str, can_access: bool = True) -> bool:
        key = (knox_id, chatbot_id)
        now = datetime.utcnow()

        if key in self._permissions:
            self._permissions[key]["can_access"] = can_access
        else:
            new_id = max(p["id"] for p in self._permissions.values()) + 1 if self._permissions else 1
            self._permissions[key] = {
                "id": new_id,
                "knox_id": knox_id,
                "chatbot_id": chatbot_id,
                "can_access": can_access,
                "created_at": now.isoformat(),
            }
        return True

    def revoke_access(self, knox_id: str, chatbot_id: str) -> bool:
        key = (knox_id, chatbot_id)
        if key in self._permissions:
            del self._permissions[key]
            return True
        return False

    def get_chatbot_users(self, chatbot_id: str) -> List[dict]:
        return [
            p for (k, c), p in self._permissions.items()
            if c == chatbot_id and p["can_access"]
        ]

    def get_all_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        return list(self._permissions.values())[skip:skip+limit]

    # DB 권한 메서드 (Mock)
    def get_user_db_permissions(self, knox_id: str) -> List[dict]:
        """Mock: 모든 DB에 접근 가능으로 반환"""
        return []

    def grant_db_access(self, knox_id: str, db_id: str, can_access: bool = True) -> bool:
        """Mock: 항상 성공"""
        return True

    def revoke_db_access(self, knox_id: str, db_id: str) -> bool:
        """Mock: 항상 성공"""
        return True

    def get_all_db_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        """Mock: 빈 목록 반환"""
        return []


# ── PostgreSQL 구현체 ─────────────────────────────────────────────
class PGPermissionRepository(PermissionRepository):
    """PostgreSQL 기반 권한 저장소"""

    def __init__(self, session: Session):
        self.session = session

    def get_user_permissions(self, knox_id: str) -> List[dict]:
        rows = self.session.query(UserChatbotAccess).filter_by(knox_id=knox_id).all()
        return [r.to_dict() for r in rows]

    def check_access(self, knox_id: str, chatbot_id: str) -> bool:
        """
        특정 챗봇 접근 권한 확인 (PostgreSQL)
        - 권한이 없으면 기본적으로 허용 (True)
        - 명시적으로 차단된 경우만 차단 (can_access=False)
        """
        row = self.session.query(UserChatbotAccess).filter_by(
            knox_id=knox_id,
            chatbot_id=chatbot_id,
        ).first()
        if not row:
            return True  # 기본값: 허용
        return row.can_access

    def grant_access(self, knox_id: str, chatbot_id: str, can_access: bool = True) -> bool:
        existing = self.session.query(UserChatbotAccess).filter_by(
            knox_id=knox_id,
            chatbot_id=chatbot_id
        ).first()

        if existing:
            existing.can_access = can_access
        else:
            new_perm = UserChatbotAccess(
                knox_id=knox_id,
                chatbot_id=chatbot_id,
                can_access=can_access
            )
            self.session.add(new_perm)

        self.session.commit()
        return True

    def revoke_access(self, knox_id: str, chatbot_id: str) -> bool:
        result = self.session.query(UserChatbotAccess).filter_by(
            knox_id=knox_id,
            chatbot_id=chatbot_id
        ).delete()
        self.session.commit()
        return result > 0

    def get_chatbot_users(self, chatbot_id: str) -> List[dict]:
        rows = self.session.query(UserChatbotAccess).filter_by(
            chatbot_id=chatbot_id,
            can_access=True
        ).all()
        return [r.to_dict() for r in rows]

    def get_all_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        rows = self.session.query(UserChatbotAccess).offset(skip).limit(limit).all()
        return [r.to_dict() for r in rows]

    # DB 권한 메서드 (PostgreSQL)
    def get_user_db_permissions(self, knox_id: str) -> List[dict]:
        rows = self.session.query(UserDbAccess).filter_by(knox_id=knox_id).all()
        return [r.to_dict() for r in rows]

    def grant_db_access(self, knox_id: str, db_id: str, can_access: bool = True) -> bool:
        existing = self.session.query(UserDbAccess).filter_by(
            knox_id=knox_id,
            db_id=db_id
        ).first()

        if existing:
            existing.can_access = can_access
        else:
            new_perm = UserDbAccess(
                knox_id=knox_id,
                db_id=db_id,
                can_access=can_access
            )
            self.session.add(new_perm)

        self.session.commit()
        return True

    def revoke_db_access(self, knox_id: str, db_id: str) -> bool:
        result = self.session.query(UserDbAccess).filter_by(
            knox_id=knox_id,
            db_id=db_id
        ).delete()
        self.session.commit()
        return result > 0

    def get_all_db_permissions(self, skip: int = 0, limit: int = 100) -> List[dict]:
        rows = self.session.query(UserDbAccess).offset(skip).limit(limit).all()
        return [r.to_dict() for r in rows]


# ── 팩토리 함수 ────────────────────────────────────────────────────
def get_permission_repository(
    use_mock: bool = True,
    session: Optional[Session] = None
) -> PermissionRepository:
    """
    설정에 따라 적절한 Repository 반환
    """
    if use_mock:
        return MockPermissionRepository()
    # 실제 DB 사용 시 session 필수
    if session is None:
        from backend.database.session import SessionLocal
        db = SessionLocal()
        try:
            return PGPermissionRepository(db)
        except:
            db.close()
            raise
    return PGPermissionRepository(session)


# ── FastAPI 의존성 주입용 ─────────────────────────────────────────
from backend.config import settings
from backend.database.session import get_db_session
from fastapi import Depends


def get_perm_repo(db: Session = Depends(get_db_session)) -> PermissionRepository:
    """
    FastAPI Depends용 PermissionRepository 제공자
    
    사용 예:
        @router.get("/users/{knox_id}")
        async def get_user(
            knox_id: str,
            repo: PermissionRepository = Depends(get_perm_repo),
        ):
            ...
    """
    return get_permission_repository(use_mock=settings.USE_MOCK_DB, session=db)
