"""
backend/models/delegation_chain.py - DelegationChain SQLAlchemy Model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Text
from sqlalchemy.orm import relationship

from backend.database.session import Base


class DelegationChain(Base):
    """위임 체인 모델 - Agent 계층 구조 추적"""
    
    __tablename__ = 'delegation_chains'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    # Using String instead of UUID for compatibility
    session_id = Column(
        String(36),
        ForeignKey('sessions.session_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    parent_agent = Column(String(100), nullable=False)
    child_agent = Column(String(100), nullable=False)
    delegation_reason = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationship
    session = relationship("ChatSession", back_populates="delegation_chains")
    
    def to_dict(self) -> dict:
        """Dictionary 변환"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "parent_agent": self.parent_agent,
            "child_agent": self.child_agent,
            "delegation_reason": self.delegation_reason,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f"<DelegationChain(id={self.id}, parent={self.parent_agent}, child={self.child_agent})>"
