"""
backend/conversation/repository.py - Conversation History Repository
대화 히스토리 저장 및 조회를 위한 Repository
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session as SQLSession

from backend.config import settings

Base = declarative_base()


# ── 데이터 모델 ─────────────────────────────────────────────────────
@dataclass
class ConversationLog:
    id: Optional[int]
    session_id: str
    knox_id: str
    chatbot_id: str
    user_message: str
    assistant_response: str
    tokens_used: int
    latency_ms: int
    search_results_count: int
    confidence_score: Optional[float]
    delegated_to: Optional[str]
    created_at: datetime


# ── SQLAlchemy 모델 ───────────────────────────────────────────────
class ConversationLogORM(Base):
    __tablename__ = 'conversation_logs'
    __table_args__ = {'schema': 'test'}
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False, index=True)
    knox_id = Column(String(50), nullable=False, index=True)
    chatbot_id = Column(String(50), nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    search_results_count = Column(Integer, default=0)
    confidence_score = Column(Float, nullable=True)
    delegated_to = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Repository 인터페이스 ─────────────────────────────────────────
class ConversationRepository(ABC):
    @abstractmethod
    def save(self, log: ConversationLog) -> ConversationLog:
        pass
    
    @abstractmethod
    def get_by_session(self, session_id: str, limit: int = 100) -> List[ConversationLog]:
        pass
    
    @abstractmethod
    def get_by_user(self, knox_id: str, limit: int = 100) -> List[ConversationLog]:
        pass
    
    @abstractmethod
    def get_by_chatbot(self, chatbot_id: str, limit: int = 100) -> List[ConversationLog]:
        pass
    
    @abstractmethod
    def get_stats(self, knox_id: Optional[str] = None) -> dict:
        pass


# ── Mock Repository (개발/테스트용) ────────────────────────────────
class MockConversationRepository(ConversationRepository):
    """인메모리 Mock 구현"""
    
    def __init__(self):
        self._logs: List[ConversationLog] = []
        self._id_counter = 1
        self._init_sample_data()
    
    def _init_sample_data(self):
        """샘플 데이터 초기화"""
        from datetime import datetime, timedelta
        
        sample_data = [
            ConversationLog(
                id=1,
                session_id="sess-001",
                knox_id="user-001",
                chatbot_id="chatbot-hr",
                user_message="연차 신청은 어떻게 하나요?",
                assistant_response="연차 신청은 HR 시스템에서 가능합니다.",
                tokens_used=245,
                latency_ms=1200,
                search_results_count=5,
                confidence_score=85.5,
                delegated_to=None,
                created_at=datetime.now() - timedelta(hours=2)
            ),
            ConversationLog(
                id=2,
                session_id="sess-001",
                knox_id="user-001",
                chatbot_id="chatbot-hr-benefit",
                user_message="4대보험은 어떤 것들이 있나요?",
                assistant_response="국민연금, 건강보험, 고용보험, 산재보험이 포함됩니다.",
                tokens_used=189,
                latency_ms=980,
                search_results_count=3,
                confidence_score=65.0,
                delegated_to="chatbot-hr-benefit",
                created_at=datetime.now() - timedelta(hours=1)
            ),
            ConversationLog(
                id=3,
                session_id="sess-002",
                knox_id="user-002",
                chatbot_id="chatbot-tech",
                user_message="FastAPI에서 DB 연결은?",
                assistant_response="SQLAlchemy를 사용하여 연결합니다.",
                tokens_used=312,
                latency_ms=1500,
                search_results_count=8,
                confidence_score=92.0,
                delegated_to=None,
                created_at=datetime.now() - timedelta(minutes=30)
            ),
            ConversationLog(
                id=4,
                session_id="sess-003",
                knox_id="user-001",
                chatbot_id="chatbot-rtl-verilog",
                user_message="4비트 카운터 Verilog 코드",
                assistant_response="module counter4bit(...)",
                tokens_used=420,
                latency_ms=2100,
                search_results_count=6,
                confidence_score=95.0,
                delegated_to=None,
                created_at=datetime.now() - timedelta(minutes=10)
            ),
        ]
        self._logs = sample_data
        self._id_counter = 5
    
    def save(self, log: ConversationLog) -> ConversationLog:
        log.id = self._id_counter
        self._id_counter += 1
        self._logs.append(log)
        return log
    
    def get_by_session(self, session_id: str, limit: int = 100) -> List[ConversationLog]:
        return [log for log in self._logs if log.session_id == session_id][:limit]
    
    def get_by_user(self, knox_id: str, limit: int = 100) -> List[ConversationLog]:
        return [log for log in self._logs if log.knox_id == knox_id][:limit]
    
    def get_by_chatbot(self, chatbot_id: str, limit: int = 100) -> List[ConversationLog]:
        return [log for log in self._logs if log.chatbot_id == chatbot_id][:limit]
    
    def get_stats(self, knox_id: Optional[str] = None) -> dict:
        logs = self._logs
        if knox_id:
            logs = [log for log in logs if log.knox_id == knox_id]
        
        if not logs:
            return {
                "total_conversations": 0,
                "total_messages": 0,
                "avg_latency_ms": 0,
                "avg_confidence": 0,
            }
        
        return {
            "total_conversations": len(set(log.session_id for log in logs)),
            "total_messages": len(logs),
            "avg_latency_ms": sum(log.latency_ms for log in logs) / len(logs),
            "avg_confidence": sum(log.confidence_score or 0 for log in logs) / len(logs),
            "total_tokens": sum(log.tokens_used for log in logs),
        }


# ── PostgreSQL Repository (운영용) ───────────────────────────────
class PGConversationRepository(ConversationRepository):
    """PostgreSQL 구현"""
    
    def __init__(self, db_url: str):
        self._engine = create_engine(db_url)
        self._Session = sessionmaker(bind=self._engine)
    
    def _to_model(self, orm: ConversationLogORM) -> ConversationLog:
        return ConversationLog(
            id=orm.id,
            session_id=orm.session_id,
            knox_id=orm.knox_id,
            chatbot_id=orm.chatbot_id,
            user_message=orm.user_message,
            assistant_response=orm.assistant_response,
            tokens_used=orm.tokens_used or 0,
            latency_ms=orm.latency_ms or 0,
            search_results_count=orm.search_results_count or 0,
            confidence_score=orm.confidence_score,
            delegated_to=orm.delegated_to,
            created_at=orm.created_at,
        )
    
    def save(self, log: ConversationLog) -> ConversationLog:
        with self._Session() as session:
            orm = ConversationLogORM(
                session_id=log.session_id,
                knox_id=log.knox_id,
                chatbot_id=log.chatbot_id,
                user_message=log.user_message,
                assistant_response=log.assistant_response,
                tokens_used=log.tokens_used,
                latency_ms=log.latency_ms,
                search_results_count=log.search_results_count,
                confidence_score=log.confidence_score,
                delegated_to=log.delegated_to,
            )
            session.add(orm)
            session.commit()
            session.refresh(orm)
            return self._to_model(orm)
    
    def get_by_session(self, session_id: str, limit: int = 100) -> List[ConversationLog]:
        with self._Session() as session:
            results = session.query(ConversationLogORM).filter(
                ConversationLogORM.session_id == session_id
            ).order_by(ConversationLogORM.created_at.desc()).limit(limit).all()
            return [self._to_model(r) for r in results]
    
    def get_by_user(self, knox_id: str, limit: int = 100) -> List[ConversationLog]:
        with self._Session() as session:
            results = session.query(ConversationLogORM).filter(
                ConversationLogORM.knox_id == knox_id
            ).order_by(ConversationLogORM.created_at.desc()).limit(limit).all()
            return [self._to_model(r) for r in results]
    
    def get_by_chatbot(self, chatbot_id: str, limit: int = 100) -> List[ConversationLog]:
        with self._Session() as session:
            results = session.query(ConversationLogORM).filter(
                ConversationLogORM.chatbot_id == chatbot_id
            ).order_by(ConversationLogORM.created_at.desc()).limit(limit).all()
            return [self._to_model(r) for r in results]
    
    def get_stats(self, knox_id: Optional[str] = None) -> dict:
        from sqlalchemy import func
        
        with self._Session() as session:
            query = session.query(
                func.count(ConversationLogORM.id).label('total'),
                func.avg(ConversationLogORM.latency_ms).label('avg_latency'),
                func.avg(ConversationLogORM.confidence_score).label('avg_confidence'),
                func.sum(ConversationLogORM.tokens_used).label('total_tokens'),
            )
            
            if knox_id:
                query = query.filter(ConversationLogORM.knox_id == knox_id)
            
            result = query.first()
            
            # 세션 수 계산
            session_query = session.query(func.count(func.distinct(ConversationLogORM.session_id)))
            if knox_id:
                session_query = session_query.filter(ConversationLogORM.knox_id == knox_id)
            session_count = session_query.scalar()
            
            return {
                "total_conversations": session_count or 0,
                "total_messages": result.total or 0,
                "avg_latency_ms": round(result.avg_latency or 0, 2),
                "avg_confidence": round(result.avg_confidence or 0, 2),
                "total_tokens": result.total_tokens or 0,
            }


# ── Factory ───────────────────────────────────────────────────────
def get_conversation_repository() -> ConversationRepository:
    """환경 설정에 따라 적절한 Repository 반환"""
    if settings.USE_MOCK_DB:
        return MockConversationRepository()
    else:
        return PGConversationRepository(settings.DATABASE_URL)
