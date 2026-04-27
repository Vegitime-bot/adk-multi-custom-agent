"""
backend/repository/delegation_repository.py - Delegation Repository
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc

from backend.models.delegation_chain import DelegationChain


class DelegationRepository(ABC):
    """위임 체인 저장소 인터페이스"""
    
    @abstractmethod
    def create(self, session_id: str, parent_agent: str, 
               child_agent: str, delegation_reason: Optional[str] = None,
               confidence_score: Optional[float] = None) -> DelegationChain:
        """위임 기록 생성"""
        pass
    
    @abstractmethod
    def get_by_session(self, session_id: str) -> List[DelegationChain]:
        """세션별 위임 체인 조회"""
        pass
    
    @abstractmethod
    def get_chain_path(self, session_id: str) -> List[Dict[str, Any]]:
        """위임 경로 반환 (순서대로)"""
        pass


class PostgreSQLDelegationRepository(DelegationRepository):
    """PostgreSQL 위임 체인 저장소"""
    
    def __init__(self, db: DBSession):
        self.db = db
    
    def create(self, session_id: str, parent_agent: str, 
               child_agent: str, delegation_reason: Optional[str] = None,
               confidence_score: Optional[float] = None) -> DelegationChain:
        """위임 기록 생성"""
        from uuid import UUID
        
        delegation = DelegationChain(
            session_id=UUID(session_id),
            parent_agent=parent_agent,
            child_agent=child_agent,
            delegation_reason=delegation_reason,
            confidence_score=confidence_score
        )
        
        self.db.add(delegation)
        self.db.commit()
        self.db.refresh(delegation)
        return delegation
    
    def get_by_session(self, session_id: str) -> List[DelegationChain]:
        """세션별 위임 체인 조회"""
        from uuid import UUID
        
        return self.db.query(DelegationChain).filter(
            DelegationChain.session_id == UUID(session_id)
        ).order_by(
            DelegationChain.created_at
        ).all()
    
    def get_chain_path(self, session_id: str) -> List[Dict[str, Any]]:
        """위임 경로 반환 (순서대로)"""
        delegations = self.get_by_session(session_id)
        
        path = []
        for d in delegations:
            path.append({
                "from": d.parent_agent,
                "to": d.child_agent,
                "reason": d.delegation_reason,
                "confidence": d.confidence_score,
                "time": d.created_at.isoformat() if d.created_at else None
            })
        
        return path
