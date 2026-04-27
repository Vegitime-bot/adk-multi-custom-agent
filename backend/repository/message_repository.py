"""
backend/repository/message_repository.py - Message Repository
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc

from backend.models.message import Message


class MessageRepository(ABC):
    """메시지 저장소 인터페이스"""
    
    @abstractmethod
    def create(self, session_id: str, role: str, content: str,
               tokens_used: int = 0, latency_ms: int = 0,
               confidence_score: Optional[float] = None,
               delegated_to: Optional[str] = None) -> Message:
        """메시지 생성"""
        pass
    
    @abstractmethod
    def get_by_session(self, session_id: str, limit: int = 30,
                       offset: int = 0) -> List[Message]:
        """세션별 메시지 조회 (시간순, 페이지네이션)"""
        pass
    
    @abstractmethod
    def get_by_session_all(self, session_id: str) -> List[Message]:
        """세션별 모든 메시지 조회"""
        pass
    
    @abstractmethod
    def get_message_count(self, session_id: str) -> int:
        """세션별 메시지 총 개수"""
        pass


class PostgreSQLMessageRepository(MessageRepository):
    """PostgreSQL 메시지 저장소"""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create(self, session_id: str, role: str, content: str,
               tokens_used: int = 0, latency_ms: int = 0,
               confidence_score: Optional[float] = None,
               delegated_to: Optional[str] = None) -> Message:
        """메시지 생성"""
        from uuid import UUID
        
        message = Message(
            session_id=UUID(session_id),
            role=role,
            content=content,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            confidence_score=confidence_score,
            delegated_to=delegated_to
        )
        
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        
        # 세션 메시지 카운트 업데이트
        from backend.models.chat_session import ChatSession
        session = self.db.query(ChatSession).filter(
            ChatSession.session_id == UUID(session_id)
        ).first()
        if session:
            session.increment_message_count()
            session.touch()
            self.db.commit()
        
        return message
    
    def get_by_session(self, session_id: str, limit: int = 30,
                       offset: int = 0) -> List[Message]:
        """세션별 메시지 조회 (시간순, 페이지네이션)"""
        from uuid import UUID
        
        return self.db.query(Message).filter(
            Message.session_id == UUID(session_id)
        ).order_by(
            desc(Message.created_at)
        ).offset(offset).limit(limit).all()
    
    def get_by_session_all(self, session_id: str) -> List[Message]:
        """세션별 모든 메시지 조회"""
        from uuid import UUID
        
        return self.db.query(Message).filter(
            Message.session_id == UUID(session_id)
        ).order_by(
            Message.created_at
        ).all()
    
    def get_message_count(self, session_id: str) -> int:
        """세션별 메시지 총 개수"""
        from uuid import UUID
        from sqlalchemy import func
        
        return self.db.query(func.count(Message.message_id)).filter(
            Message.session_id == UUID(session_id)
        ).scalar() or 0
