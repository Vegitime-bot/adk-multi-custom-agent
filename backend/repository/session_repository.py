"""
backend/repository/session_repository.py - Session Repository
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc, func

from backend.models.chat_session import ChatSession


class SessionRepository(ABC):
    """세션 저장소 인터페이스"""
    
    @abstractmethod
    def create(self, user_id: str, chatbot_id: str, 
               session_id: Optional[str] = None) -> ChatSession:
        """새 세션 생성"""
        pass
    
    @abstractmethod
    def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        """ID로 세션 조회"""
        pass
    
    @abstractmethod
    def list_by_user(self, user_id: str, limit: int = 30, 
                     offset: int = 0) -> List[ChatSession]:
        """사용자별 세션 목록 (페이지네이션)"""
        pass
    
    @abstractmethod
    def update_last_accessed(self, session_id: str) -> bool:
        """last_accessed 업데이트"""
        pass
    
    @abstractmethod
    def delete_old_sessions(self, days: int = 30) -> int:
        """오래된 세션 삭제, 삭제된 행 수 반환"""
        pass
    
    @abstractmethod
    def get_user_session_count(self, user_id: str) -> int:
        """사용자별 세션 총 개수"""
        pass


class PostgreSQLSessionRepository(SessionRepository):
    """PostgreSQL 세션 저장소"""
    
    def __init__(self, db_url: str):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def create(self, user_id: str, chatbot_id: str, 
               session_id: Optional[str] = None) -> ChatSession:
        """새 세션 생성"""
        with self.Session() as db:
            session = ChatSession(
                user_id=user_id,
                chatbot_id=chatbot_id
            )
            if session_id:
                try:
                    session.session_id = UUID(session_id)
                except ValueError:
                    pass
            
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
    
    def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        """ID로 세션 조회"""
        with self.Session() as db:
            try:
                uuid = UUID(session_id)
                return db.query(ChatSession).filter(
                    ChatSession.session_id == uuid
                ).first()
            except ValueError:
                return None
    
    def list_by_user(self, user_id: str, limit: int = 30, 
                     offset: int = 0) -> List[ChatSession]:
        """사용자별 세션 목록 (최근 접근 순)"""
        with self.Session() as db:
            return db.query(ChatSession).filter(
                ChatSession.user_id == user_id
            ).order_by(
                desc(ChatSession.last_accessed)
            ).offset(offset).limit(limit).all()
    
    def update_last_accessed(self, session_id: str) -> bool:
        """last_accessed 업데이트"""
        with self.Session() as db:
            session = self.get_by_id(session_id)
            if session:
                session.touch()
                db.commit()
                return True
            return False
    
    def delete_old_sessions(self, days: int = 30) -> int:
        """오래된 세션 삭제"""
        from sqlalchemy import text
        
        with self.Session() as db:
            result = db.execute(
                text("""
                    DELETE FROM sessions 
                    WHERE last_accessed < NOW() - INTERVAL ':days days'
                """),
                {'days': days}
            )
            db.commit()
            return result.rowcount
    
    def get_user_session_count(self, user_id: str) -> int:
        """사용자별 세션 총 개수"""
        with self.Session() as db:
            return db.query(func.count(ChatSession.session_id)).filter(
                ChatSession.user_id == user_id
            ).scalar() or 0
