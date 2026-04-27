"""
backend/models/message.py - Message SQLAlchemy Model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from backend.database.session import Base


class Message(Base):
    """메시지 모델"""
    
    __tablename__ = 'messages'
    
    message_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey('sessions.session_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    confidence_score = Column(Float, nullable=True)
    delegated_to = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationship
    session = relationship("ChatSession", back_populates="messages")
    
    def to_dict(self) -> dict:
        """Dictionary 변환"""
        return {
            "message_id": self.message_id,
            "session_id": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "confidence_score": self.confidence_score,
            "delegated_to": self.delegated_to,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f"<Message(id={self.message_id}, session={self.session_id}, role={self.role})>"
