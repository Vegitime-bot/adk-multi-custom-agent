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
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create(self, user_id: str, chatbot_id: str, 
               session_id: Optional[str] = None) -> ChatSession:
        """새 세션 생성"""
        session = ChatSession(
            user_id=user_id,
            chatbot_id=chatbot_id
        )
        if session_id:
            try:
                session.session_id = UUID(session_id)
            except ValueError:
                pass  # 잘못된 UUID면 자동 생성됨
        
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        """ID로 세션 조회"""
        try:
            uuid = UUID(session_id)
            return self.db.query(ChatSession).filter(
                ChatSession.session_id == uuid
            ).first()
        except ValueError:
            return None
    
    def list_by_user(self, user_id: str, limit: int = 30, 
                     offset: int = 0) -> List[ChatSession]:
        """사용자별 세션 목록 (최근 접근 순)"""
        return self.db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(
            desc(ChatSession.last_accessed)
        ).offset(offset).limit(limit).all()
    
    def update_last_accessed(self, session_id: str) -> bool:
        """last_accessed 업데이트"""
        session = self.get_by_id(session_id)
        if session:
            session.touch()
            self.db.commit()
            return True
        return False
    
    def delete_old_sessions(self, days: int = 30) -> int:
        """오래된 세션 삭제"""
        from sqlalchemy import text
        
        result = self.db.execute(
            text("""
                DELETE FROM sessions 
                WHERE last_accessed < NOW() - INTERVAL ':days days'
            """),
            {'days': days}
        )
        self.db.commit()
        return result.rowcount
    
    def get_user_session_count(self, user_id: str) -> int:
        """사용자별 세션 총 개수"""
        return self.db.query(func.count(ChatSession.session_id)).filter(
            ChatSession.user_id == user_id
        ).scalar() or 0
