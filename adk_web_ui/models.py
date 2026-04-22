"""
Pydantic Models for ADK Web UI
Knox ID 기반 사용자 분리 + 관리자 기능
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


# ============================================
# User Models
# ============================================

class User(BaseModel):
    """사용자 모델"""
    knox_id: str = Field(..., description="Knox 플랫폼 사용자 ID")
    created_at: datetime
    last_active: Optional[datetime] = None
    is_admin: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "knox_id": "knox_user_001",
                "created_at": "2026-04-22T10:00:00",
                "last_active": "2026-04-22T15:30:00",
                "is_admin": False
            }
        }


class UserCreate(BaseModel):
    """사용자 생성 요청"""
    knox_id: str = Field(..., min_length=1, max_length=255)
    
    @validator('knox_id')
    def validate_knox_id(cls, v):
        if not v or v.strip() == '':
            raise ValueError('knox_id는 필수입니다')
        return v.strip()


class UserStats(BaseModel):
    """사용자 통계"""
    knox_id: str
    is_admin: bool
    user_created: datetime
    session_count: int = 0
    message_count: int = 0
    last_message_time: Optional[datetime] = None


# ============================================
# Session Models
# ============================================

class Session(BaseModel):
    """세션 모델"""
    session_id: str
    knox_id: str
    created_at: datetime
    updated_at: datetime
    initial_agent: Optional[str] = None
    is_active: bool = True
    message_count: Optional[int] = 0
    delegation_chain: Optional[List[str]] = []
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123",
                "knox_id": "knox_user_001",
                "created_at": "2026-04-22T10:00:00",
                "updated_at": "2026-04-22T15:30:00",
                "initial_agent": "chatbot_company_adk",
                "is_active": True,
                "message_count": 10,
                "delegation_chain": ["chatbot_company_adk", "chatbot_hr_adk"]
            }
        }


class SessionCreate(BaseModel):
    """세션 생성 요청"""
    agent: str = Field(..., description="초기 Agent ID")
    knox_id: str = Field(..., description="사용자 Knox ID")
    
    @validator('agent')
    def validate_agent(cls, v):
        valid_agents = [
            "chatbot_company_adk",
            "chatbot_hr_adk", 
            "chatbot_tech_adk"
        ]
        if v not in valid_agents:
            raise ValueError(f'유효하지 않은 Agent입니다: {v}')
        return v


class SessionReset(BaseModel):
    """세션 초기화 요청"""
    session_id: str
    knox_id: str  # 권한 확인용


# ============================================
# Message Models
# ============================================

class Message(BaseModel):
    """메시지 모델"""
    id: Optional[int] = None
    session_id: str
    role: str = Field(..., regex="^(user|assistant)$")
    content: str
    agent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "session_id": "sess_abc123",
                "role": "user",
                "content": "안녕하세요",
                "agent_id": "chatbot_company_adk",
                "created_at": "2026-04-22T10:00:00"
            }
        }


class MessageCreate(BaseModel):
    """메시지 생성 요청"""
    session_id: str
    role: str
    content: str
    agent_id: Optional[str] = None


# ============================================
# Chat Models
# ============================================

class ChatRequest(BaseModel):
    """채팅 요청 (Phase 2: Knox ID 추가)"""
    agent: str = Field(..., description="대상 Agent ID")
    message: str = Field(..., min_length=1, description="사용자 메시지")
    session_id: str = Field(..., description="세션 ID")
    knox_id: str = Field(..., description="사용자 Knox ID")
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('메시지는 비어있을 수 없습니다')
        if len(v) > 10000:
            raise ValueError('메시지는 10000자를 초과할 수 없습니다')
        return v.strip()


class ChatResponse(BaseModel):
    """채팅 응답"""
    response: str
    session_id: str
    agent_used: str
    delegation_chain: List[str]
    debug_info: dict


# ============================================
# Admin Models
# ============================================

class AdminStats(BaseModel):
    """관리자 대시보드 통계"""
    total_users: int
    admin_count: int
    active_sessions: int
    total_sessions: int
    total_messages: int
    user_messages: int
    assistant_messages: int
    last_message_time: Optional[datetime] = None


class AdminSessionQuery(BaseModel):
    """관리자 세션 조회 파라미터"""
    knox_id: Optional[str] = None
    agent: Optional[str] = None
    is_active: Optional[bool] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AdminLoginRequest(BaseModel):
    """관리자 로그인 요청"""
    knox_id: str
    admin_key: Optional[str] = None  # 향후 확장용


# ============================================
# Agent Models
# ============================================

class AgentInfo(BaseModel):
    """Agent 정보"""
    id: str
    name: str
    description: str
    level: int
    app_name: str
    sub_agents: List[str] = []
    parent: Optional[str] = None


class AgentListResponse(BaseModel):
    """Agent 목록 응답"""
    agents: List[AgentInfo]


# ============================================
# Error Models
# ============================================

class ErrorResponse(BaseModel):
    """에러 응답"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class ValidationError(BaseModel):
    """검증 에러"""
    loc: List[str]
    msg: str
    type: str
