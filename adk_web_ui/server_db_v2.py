"""
ADK Web UI Server - PostgreSQL Mode v2
Knox ID 기반 저장 + 관리자 기능 + Phase 2 개선사항

개선사항:
- 설정 외부화 (config.py)
- 구조화된 로깅
- OpenAPI/Swagger 문서화
- 메시지 검색 API
- 세션 이름 변경
- 파일 첨부 (Mock)
- 메시지 복사/삭제
- 무한 스크롤 (페이지네이션)
- 대화 내역 내보내기
- 읽음 확인
"""

import sys
import os
import json
import logging
import logging.config
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import io
import csv

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import (
    FastAPI, HTTPException, Header, Depends, Query, UploadFile, File,
    BackgroundTasks, Request
)
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

# 설정 로드
from config import (
    settings, AGENT_CONFIGS, KEYWORD_DELEGATION, 
    LOGGING_CONFIG, OPENAPI_TAGS, OPENAPI_DESCRIPTION
)

# 로깅 설정
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("adk_web_ui")

# Agent 임포트 (존재하는 경우)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
    from chatbot_company_adk import root_agent as company_agent
    from chatbot_hr_adk import root_agent as hr_agent
    from chatbot_tech_adk import root_agent as tech_agent
    AGENTS_AVAILABLE = True
except ImportError:
    logger.warning("ADK agents not available, using mock mode")
    AGENTS_AVAILABLE = False
    company_agent = hr_agent = tech_agent = None

# FastAPI 앱 생성
app = FastAPI(
    title="ADK Web UI Server",
    description=OPENAPI_DESCRIPTION,
    version="2.0.0",
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS.split(","),
    allow_headers=settings.CORS_ALLOW_HEADERS.split(","),
)

# DB 연결 풀 초기화
db_pool = None

def init_db_pool():
    """DB 연결 풀 초기화"""
    global db_pool
    try:
        db_pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=settings.DB_POOL_SIZE,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD
        )
        logger.info(f"Database pool initialized (size: {settings.DB_POOL_SIZE})")
    except Exception as e:
        logger.error(f"Failed to initialize DB pool: {e}")
        raise

@contextmanager
def get_db_connection():
    """DB 연결 컨텍스트 매니저"""
    conn = None
    try:
        conn = db_pool.getconn()
        yield conn
    finally:
        if conn:
            db_pool.putconn(conn)

# ==========================================
# Pydantic Models
# ==========================================

class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    agent: str = Field(..., description="Agent ID", example="chatbot_company_adk")
    message: str = Field(..., description="사용자 메시지", example="안녕하세요")
    session_id: str = Field(..., description="세션 ID", example="session_123456")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent": "chatbot_company_adk",
                "message": "안녕하세요",
                "session_id": "session_123456"
            }
        }

class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    response: str = Field(..., description="Agent 응답")
    session_id: str = Field(..., description="세션 ID")
    agent_used: str = Field(..., description="실제 처리한 Agent ID")
    delegation_chain: List[str] = Field(..., description="위임 체인")
    message_id: Optional[int] = Field(None, description="메시지 ID")
    debug_info: Optional[Dict] = Field(None, description="디버그 정보")

class ResetRequest(BaseModel):
    """세션 초기화 요청"""
    session_id: str = Field(..., description="세션 ID")

class SessionRenameRequest(BaseModel):
    """세션 이름 변경 요청"""
    session_id: str = Field(..., description="세션 ID")
    name: str = Field(..., min_length=1, max_length=100, description="새 세션 이름")

class MessageSearchRequest(BaseModel):
    """메시지 검색 요청"""
    session_id: str = Field(..., description="세션 ID")
    query: str = Field(..., min_length=1, description="검색어")
    limit: int = Field(default=20, ge=1, le=100, description="검색 결과 수")

class MessageDeleteRequest(BaseModel):
    """메시지 삭제 요청"""
    message_id: int = Field(..., description="메시지 ID")

class ExportRequest(BaseModel):
    """내보내기 요청"""
    session_ids: List[str] = Field(..., description="내보낼 세션 ID 목록")
    format: str = Field(default="json", pattern="^(json|txt|csv)$", description="내보내기 형식")

class MarkReadRequest(BaseModel):
    """읽음 표시 요청"""
    session_id: str = Field(..., description="세션 ID")
    message_ids: Optional[List[int]] = Field(None, description="읽음 처리할 메시지 ID 목록 (None=모든 메시지)")

class PaginatedResponse(BaseModel):
    """페이지네이션 응답 베이스"""
    total: int = Field(..., description="전체 항목 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")
    has_prev: bool = Field(..., description="이전 페이지 존재 여부")

class MessageResponse(BaseModel):
    """메시지 응답 모델"""
    id: int
    role: str
    content: str
    agent_id: Optional[str]
    created_at: datetime
    is_read: bool = Field(default=False, description="읽음 여부")
    read_at: Optional[datetime] = Field(None, description="읽은 시간")

# ==========================================
# Helper Functions
# ==========================================

def is_admin(knox_id: str) -> bool:
    """관리자 여부 확인"""
    if not knox_id:
        return False
    if knox_id in settings.admin_knox_ids_list:
        return True
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM admin_users WHERE knox_id = %s', (knox_id,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        return False

def check_delegation(current_agent: str, message: str) -> tuple:
    """키워드 기반 위임 체크"""
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    message_lower = message.lower()
    for keyword, target in keywords.items():
        if keyword in message_lower:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"

def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    """Mock 응답 생성"""
    config = AGENT_CONFIGS.get(agent_id, {})
    display_name = config.get("display_name", agent_id)
    return f"[{display_name}] 응답\n\n📨 {message}\n🔗 {' → '.join(delegation_chain)}"

def require_knox_id(x_knox_id: Optional[str] = Header(None, alias="x-knox-id")) -> str:
    """Knox ID 필수 체크"""
    if not x_knox_id:
        logger.warning("Request without Knox ID")
        raise HTTPException(status_code=401, detail="Knox ID required in x-knox-id header")
    return x_knox_id

def require_admin(knox_id: str = Depends(require_knox_id)) -> str:
    """관리자 권한 체크"""
    if not is_admin(knox_id):
        logger.warning(f"Admin access denied for: {knox_id}")
        raise HTTPException(status_code=403, detail="Admin access required")
    return knox_id

# ==========================================
# Database Operations
# ==========================================

def save_message(session_id: str, role: str, content: str, agent_id: str) -> int:
    """메시지 저장 및 ID 반환"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO messages (session_id, role, content, agent_id)
               VALUES (%s, %s, %s, %s) RETURNING id''',
            (session_id, role, content, agent_id)
        )
        message_id = cursor.fetchone()[0]
        conn.commit()
        return message_id

def save_session(session_id: str, knox_id: str, initial_agent: str, name: Optional[str] = None):
    """세션 저장/업데이트"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (session_id, knox_id, initial_agent, name, is_active)
            VALUES (%s, %s, %s, %s, 1)
            ON CONFLICT (session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        ''', (session_id, knox_id, initial_agent, name or f"세션 {session_id[-6:]}"))
        conn.commit()

def update_session_name(session_id: str, knox_id: str, name: str) -> bool:
    """세션 이름 업데이트"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sessions SET name = %s, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = %s AND knox_id = %s
        ''', (name, session_id, knox_id))
        conn.commit()
        return cursor.rowcount > 0

def save_delegation_chain(session_id: str, chain: List[str]):
    """위임 체인 저장"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
        for idx, agent_id in enumerate(chain):
            cursor.execute(
                'INSERT INTO delegation_chains (session_id, agent_id, order_index) VALUES (%s, %s, %s)',
                (session_id, agent_id, idx)
            )
        conn.commit()

def get_session_history(session_id: str, knox_id: str, page: int = 1, page_size: int = 50) -> Dict:
    """페이지네이션 지원 히스토리 조회"""
    offset = (page - 1) * page_size
    
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인 및 전체 메시지 수 조회
        cursor.execute('''
            SELECT COUNT(*) as total FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE m.session_id = %s AND s.knox_id = %s
        ''', (session_id, knox_id))
        total = cursor.fetchone()['total']
        
        # 메시지 조회 (페이지네이션)
        cursor.execute('''
            SELECT m.id, m.role, m.content, m.agent_id, m.created_at,
                   COALESCE(mr.is_read, false) as is_read, mr.read_at
            FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            LEFT JOIN message_read_status mr ON m.id = mr.message_id
            WHERE m.session_id = %s AND s.knox_id = %s
            ORDER BY m.created_at ASC
            LIMIT %s OFFSET %s
        ''', (session_id, knox_id, page_size, offset))
        rows = cursor.fetchall()
        
        # 위임 체인 조회
        cursor.execute('''
            SELECT agent_id FROM delegation_chains
            WHERE session_id = %s ORDER BY order_index ASC
        ''', (session_id,))
        chain = [row['agent_id'] for row in cursor.fetchall()]
        
        return {
            "history": [dict(row) for row in rows],
            "delegation_chain": chain,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": total > (page * page_size),
            "has_prev": page > 1
        }

def get_user_sessions(knox_id: str, page: int = 1, page_size: int = 20) -> Dict:
    """사용자 세션 목록 (페이지네이션)"""
    offset = (page - 1) * page_size
    
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 전체 세션 수
        cursor.execute(
            'SELECT COUNT(*) as total FROM sessions WHERE knox_id = %s AND is_active = 1',
            (knox_id,)
        )
        total = cursor.fetchone()['total']
        
        # 세션 목록
        cursor.execute('''
            SELECT s.session_id, s.name, s.created_at, s.updated_at, s.initial_agent, s.is_active,
                   COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            WHERE s.knox_id = %s AND s.is_active = 1
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT %s OFFSET %s
        ''', (knox_id, page_size, offset))
        sessions = cursor.fetchall()
        
        # 각 세션의 위임 체인 조회
        for session in sessions:
            cursor.execute('''
                SELECT agent_id FROM delegation_chains
                WHERE session_id = %s ORDER BY order_index ASC
            ''', (session['session_id'],))
            session['delegation_chain'] = [row['agent_id'] for row in cursor.fetchall()]
        
        return {
            "sessions": [dict(s) for s in sessions],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": total > (page * page_size),
            "has_prev": page > 1
        }

def reset_session(session_id: str, knox_id: str):
    """세션 초기화"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT 1 FROM sessions WHERE session_id = %s AND knox_id = %s',
            (session_id, knox_id)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Access denied")
        
        cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
        cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
        cursor.execute('UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s', (session_id,))
        conn.commit()

def delete_session(session_id: str, knox_id: str):
    """세션 삭제 (소프트 삭제)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT 1 FROM sessions WHERE session_id = %s AND knox_id = %s',
            (session_id, knox_id)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=403, detail="Access denied")
        
        cursor.execute(
            'UPDATE sessions SET is_active = 0 WHERE session_id = %s',
            (session_id,)
        )
        conn.commit()

def delete_message(message_id: int, knox_id: str):
    """메시지 삭제"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM messages
            WHERE id = %s AND session_id IN (
                SELECT session_id FROM sessions WHERE knox_id = %s
            )
        ''', (message_id, knox_id))
        conn.commit()
        return cursor.rowcount > 0

def search_messages_in_session(session_id: str, knox_id: str, query: str, limit: int = 20) -> List[Dict]:
    """세션 내 메시지 검색"""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT m.id, m.role, m.content, m.agent_id, m.created_at
            FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE m.session_id = %s AND s.knox_id = %s
              AND m.content ILIKE %s
            ORDER BY m.created_at DESC
            LIMIT %s
        ''', (session_id, knox_id, f"%{query}%", limit))
        return [dict(row) for row in cursor.fetchall()]

def mark_messages_read(session_id: str, knox_id: str, message_ids: Optional[List[int]] = None):
    """메시지 읽음 표시"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if message_ids:
            # 특정 메시지 읽음 처리
            cursor.execute('''
                INSERT INTO message_read_status (message_id, is_read, read_at)
                SELECT m.id, true, CURRENT_TIMESTAMP
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE m.session_id = %s AND s.knox_id = %s AND m.id = ANY(%s)
                ON CONFLICT (message_id) DO UPDATE SET is_read = true, read_at = CURRENT_TIMESTAMP
            ''', (session_id, knox_id, message_ids))
        else:
            # 세션의 모든 메시지 읽음 처리
            cursor.execute('''
                INSERT INTO message_read_status (message_id, is_read, read_at)
                SELECT m.id, true, CURRENT_TIMESTAMP
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE m.session_id = %s AND s.knox_id = %s
                ON CONFLICT (message_id) DO UPDATE SET is_read = true, read_at = CURRENT_TIMESTAMP
            ''', (session_id, knox_id))
        
        conn.commit()

def get_unread_count(session_id: str, knox_id: str) -> int:
    """읽지 않은 메시지 수 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            LEFT JOIN message_read_status mr ON m.id = mr.message_id
            WHERE m.session_id = %s AND s.knox_id = %s
              AND m.role = 'assistant'
              AND (mr.is_read = false OR mr.is_read IS NULL)
        ''', (session_id, knox_id))
        return cursor.fetchone()[0]

# ==========================================
# User API Routes
# ==========================================

@app.get("/api/agents/detail", tags=["User"])
async def get_agents_detail() -> List[Dict]:
    """모든 Agent 상세 정보 조회"""
    return [
        {
            "id": agent_id,
            "name": config.get("display_name", agent_id),
            "description": config.get("description", ""),
            "level": config.get("level", 0),
            "app_name": agent_id,
            "sub_agents": config.get("sub_agents", []),
            "parent": config.get("parent"),
            "color": config.get("color", "#667eea")
        }
        for agent_id, config in AGENT_CONFIGS.items()
    ]

@app.post("/api/run", response_model=ChatResponse, tags=["User"])
async def run_agent(request: ChatRequest, knox_id: str = Depends(require_knox_id)):
    """Agent 실행 및 메시지 전송"""
    logger.info(f"Chat request: agent={request.agent}, session={request.session_id}, user={knox_id}")
    
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    save_session(request.session_id, knox_id, request.agent)
    
    delegated_agent, reason = check_delegation(request.agent, request.message)
    chain = [request.agent] if request.agent == delegated_agent else [request.agent, delegated_agent]
    
    save_delegation_chain(request.session_id, chain)
    save_message(request.session_id, "user", request.message, request.agent)
    
    response_text = generate_mock_response(delegated_agent, request.message, chain)
    message_id = save_message(request.session_id, "assistant", response_text, delegated_agent)
    
    return ChatResponse(
        response=response_text,
        session_id=request.session_id,
        agent_used=delegated_agent,
        delegation_chain=chain,
        message_id=message_id,
        debug_info={
            "original_agent": request.agent,
            "delegated_agent": delegated_agent,
            "delegation_reason": reason,
            "agent_level": config.get("level", 0)
        }
    )

@app.post("/api/session/reset", tags=["User"])
async def reset_session_endpoint(
    request: ResetRequest,
    knox_id: str = Depends(require_knox_id)
):
    """세션 초기화 (모든 메시지 삭제)"""
    logger.info(f"Session reset: {request.session_id} by {knox_id}")
    reset_session(request.session_id, knox_id)
    return {"status": "success", "message": "Session reset successfully"}

@app.post("/api/session/rename", tags=["User"])
async def rename_session_endpoint(
    request: SessionRenameRequest,
    knox_id: str = Depends(require_knox_id)
):
    """세션 이름 변경"""
    logger.info(f"Session rename: {request.session_id} -> {request.name} by {knox_id}")
    success = update_session_name(request.session_id, knox_id, request.name)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or access denied")
    return {"status": "success", "name": request.name}

@app.get("/api/session/{session_id}/history", tags=["User"])
async def get_session_history_endpoint(
    session_id: str,
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(50, ge=1, le=100, description="페이지 크기"),
    knox_id: str = Depends(require_knox_id)
):
    """세션 히스토리 조회 (페이지네이션 지원)"""
    return get_session_history(session_id, knox_id, page, page_size)

@app.get("/api/sessions", tags=["User"])
async def list_sessions(
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    knox_id: str = Depends(require_knox_id)
):
    """사용자 세션 목록 조회 (페이지네이션 지원)"""
    return get_user_sessions(knox_id, page, page_size)

@app.delete("/api/session/{session_id}", tags=["User"])
async def delete_session_endpoint(
    session_id: str,
    knox_id: str = Depends(require_knox_id)
):
    """세션 삭제 (소프트 삭제)"""
    logger.info(f"Session delete: {session_id} by {knox_id}")
    delete_session(session_id, knox_id)
    return {"status": "success", "message": "Session deleted"}

@app.post("/api/session/{session_id}/messages/search", tags=["Search"])
async def search_messages_endpoint(
    session_id: str,
    request: MessageSearchRequest,
    knox_id: str = Depends(require_knox_id)
):
    """세션 내 메시지 검색"""
    results = search_messages_in_session(session_id, knox_id, request.query, request.limit)
    return {"results": results, "query": request.query, "count": len(results)}

@app.post("/api/messages/{message_id}/delete", tags=["User"])
async def delete_message_endpoint(
    message_id: int,
    knox_id: str = Depends(require_knox_id)
):
    """메시지 삭제"""
    success = delete_message(message_id, knox_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or access denied")
    return {"status": "success", "message_id": message_id}

@app.post("/api/session/{session_id}/read", tags=["User"])
async def mark_read_endpoint(
    session_id: str,
    request: MarkReadRequest,
    knox_id: str = Depends(require_knox_id)
):
    """메시지 읽음 표시"""
    mark_messages_read(session_id, knox_id, request.message_ids)
    return {"status": "success", "session_id": session_id}

@app.get("/api/session/{session_id}/unread", tags=["User"])
async def get_unread_count_endpoint(
    session_id: str,
    knox_id: str = Depends(require_knox_id)
):
    """읽지 않은 메시지 수 조회"""
    count = get_unread_count(session_id, knox_id)
    return {"unread_count": count, "session_id": session_id}

@app.post("/api/upload", tags=["User"])
async def upload_file(
    file: UploadFile = File(...),
    knox_id: str = Depends(require_knox_id)
):
    """파일 업로드 (Mock)"""
    if not settings.ENABLE_FILE_UPLOAD:
        raise HTTPException(status_code=403, detail="File upload disabled")
    
    # 파일 크기 체크
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_SIZE_MB}MB)")
    
    # 파일 저장
    from config import UPLOAD_DIR
    file_path = UPLOAD_DIR / f"{knox_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content)
    
    logger.info(f"File uploaded: {file_path} by {knox_id}")
    
    return {
        "status": "success",
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type,
        "url": f"/api/files/{file_path.name}"
    }

@app.post("/api/export", tags=["Export"])
async def export_sessions(
    request: ExportRequest,
    knox_id: str = Depends(require_knox_id)
):
    """대화 내역 내보내기 (JSON/TXT/CSV)"""
    if len(request.session_ids) > settings.EXPORT_MAX_SESSIONS:
        raise HTTPException(status_code=400, detail=f"Too many sessions (max {settings.EXPORT_MAX_SESSIONS})")
    
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 세션 정보 조회
        placeholders = ','.join(['%s'] * len(request.session_ids))
        cursor.execute(f'''
            SELECT s.session_id, s.name, s.created_at, s.updated_at, s.initial_agent,
                   m.role, m.content, m.agent_id, m.created_at as message_time
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            WHERE s.session_id IN ({placeholders}) AND s.knox_id = %s AND s.is_active = 1
            ORDER BY s.created_at, m.created_at
        ''', (*request.session_ids, knox_id))
        
        rows = cursor.fetchall()
    
    # 형식별 내보내기
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if request.format == "json":
        export_data = {}
        for row in rows:
            sid = row['session_id']
            if sid not in export_data:
                export_data[sid] = {
                    "session_id": sid,
                    "name": row['name'],
                    "created_at": str(row['created_at']),
                    "initial_agent": row['initial_agent'],
                    "messages": []
                }
            if row['role']:
                export_data[sid]["messages"].append({
                    "role": row['role'],
                    "content": row['content'],
                    "agent_id": row['agent_id'],
                    "time": str(row['message_time'])
                })
        
        content = json.dumps(list(export_data.values()), ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"adk_export_{timestamp}.json"
    
    elif request.format == "txt":
        lines = []
        current_session = None
        for row in rows:
            if row['session_id'] != current_session:
                current_session = row['session_id']
                lines.append(f"\n{'='*50}")
                lines.append(f"세션: {row['name']} ({row['session_id']})")
                lines.append(f"생성: {row['created_at']}")
                lines.append(f"{'='*50}\n")
            if row['role']:
                prefix = "사용자" if row['role'] == 'user' else f"Agent({row['agent_id']})"
                lines.append(f"[{row['message_time']}] {prefix}: {row['content']}\n")
        
        content = "\n".join(lines)
        media_type = "text/plain"
        filename = f"adk_export_{timestamp}.txt"
    
    elif request.format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["session_id", "session_name", "created_at", "role", "agent_id", "content", "message_time"])
        for row in rows:
            if row['role']:
                writer.writerow([
                    row['session_id'], row['name'], row['created_at'],
                    row['role'], row['agent_id'], row['content'], row['message_time']
                ])
        content = output.getvalue()
        media_type = "text/csv"
        filename = f"adk_export_{timestamp}.csv"
    
    return StreamingResponse(
        io.StringIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ==========================================
# Admin API Routes
# ==========================================

@app.get("/admin/stats", tags=["Admin"])
async def get_admin_stats(knox_id: str = Depends(require_admin)) -> Dict:
    """관리자용 통계"""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 전체 통계
        cursor.execute('SELECT COUNT(*) as total_sessions FROM sessions')
        total_sessions = cursor.fetchone()['total_sessions']
        
        cursor.execute('SELECT COUNT(*) as total_messages FROM messages')
        total_messages = cursor.fetchone()['total_messages']
        
        cursor.execute('SELECT COUNT(DISTINCT knox_id) as unique_users FROM sessions')
        unique_users = cursor.fetchone()['unique_users']
        
        # 오늘 통계
        cursor.execute('''
            SELECT COUNT(*) as today_sessions FROM sessions 
            WHERE DATE(created_at) = CURRENT_DATE
        ''')
        today_sessions = cursor.fetchone()['today_sessions']
        
        cursor.execute('''
            SELECT COUNT(*) as today_messages FROM messages 
            WHERE DATE(created_at) = CURRENT_DATE
        ''')
        today_messages = cursor.fetchone()['today_messages']
        
        # 24시간 활성 사용자
        cursor.execute('''
            SELECT COUNT(DISTINCT knox_id) as active_users_24h FROM sessions 
            WHERE updated_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ''')
        active_users_24h = cursor.fetchone()['active_users_24h']
        
        # Agent별 사용량
        cursor.execute('''
            SELECT initial_agent, COUNT(*) as count FROM sessions 
            GROUP BY initial_agent ORDER BY count DESC
        ''')
        agent_usage = [dict(row) for row in cursor.fetchall()]
        
        # 시간별 활동 (최근 7일)
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM sessions 
            WHERE created_at > CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at) ORDER BY date
        ''')
        daily_activity = [dict(row) for row in cursor.fetchall()]
        
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "unique_users": unique_users,
            "today_sessions": today_sessions,
            "today_messages": today_messages,
            "active_users_24h": active_users_24h,
            "agent_usage": agent_usage,
            "daily_activity": daily_activity
        }

@app.get("/admin/sessions", tags=["Admin"])
async def get_all_sessions_admin(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    knox_id_filter: Optional[str] = None,
    agent_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    is_active: Optional[bool] = None,
    knox_id: str = Depends(require_admin)
):
    """관리자용 전체 세션 조회 (검색/필터링 지원)"""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 동적 쿼리 구성
        where_clauses = []
        params = []
        
        if search:
            where_clauses.append("(s.session_id ILIKE %s OR s.knox_id ILIKE %s OR s.initial_agent ILIKE %s)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if knox_id_filter:
            where_clauses.append("s.knox_id = %s")
            params.append(knox_id_filter)
        
        if agent_filter:
            where_clauses.append("s.initial_agent = %s")
            params.append(agent_filter)
        
        if date_from:
            where_clauses.append("DATE(s.created_at) >= %s")
            params.append(date_from)
        
        if date_to:
            where_clauses.append("DATE(s.created_at) <= %s")
            params.append(date_to)
        
        if is_active is not None:
            where_clauses.append("s.is_active = %s")
            params.append(is_active)
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # 전체 개수
        count_query = f'SELECT COUNT(*) as total FROM sessions s {where_sql}'
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']
        
        # 세션 목록
        query = f'''
            SELECT s.*, COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            {where_sql}
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT %s OFFSET %s
        '''
        cursor.execute(query, params + [limit, offset])
        sessions = [dict(row) for row in cursor.fetchall()]
        
        # 필터 옵션
        cursor.execute('SELECT DISTINCT knox_id FROM sessions ORDER BY knox_id')
        available_users = [row['knox_id'] for row in cursor.fetchall()]
        
        cursor.execute('SELECT DISTINCT initial_agent FROM sessions ORDER BY initial_agent')
        available_agents = [row['initial_agent'] for row in cursor.fetchall()]
        
        return {
            "sessions": sessions,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "filters": {
                "available_users": available_users,
                "available_agents": available_agents
            }
        }

@app.get("/admin/sessions/search", tags=["Admin", "Search"])
async def search_sessions(
    q: str = Query(..., min_length=1, description="검색어"),
    limit: int = Query(50, ge=1, le=200),
    knox_id: str = Depends(require_admin)
):
    """세션 검색 엔드포인트"""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        search_pattern = f"%{q}%"
        cursor.execute('''
            SELECT s.*, COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            WHERE s.session_id ILIKE %s 
               OR s.knox_id ILIKE %s 
               OR s.initial_agent ILIKE %s
               OR s.name ILIKE %s
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT %s
        ''', (search_pattern, search_pattern, search_pattern, search_pattern, limit))
        
        sessions = [dict(row) for row in cursor.fetchall()]
        return {"sessions": sessions, "query": q, "count": len(sessions)}

@app.get("/admin/users", tags=["Admin"])
async def get_admin_users(
    limit: int = Query(100, ge=1, le=1000),
    knox_id: str = Depends(require_admin)
):
    """관리자용 사용자 목록 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT 
                s.knox_id,
                COUNT(DISTINCT s.session_id) as session_count,
                COUNT(m.id) as message_count,
                MIN(s.created_at) as first_seen,
                MAX(s.updated_at) as last_active,
                EXISTS(SELECT 1 FROM admin_users WHERE knox_id = s.knox_id) as is_admin
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            GROUP BY s.knox_id
            ORDER BY last_active DESC
            LIMIT %s
        ''', (limit,))
        
        users = [dict(row) for row in cursor.fetchall()]
        return {"users": users}

@app.delete("/admin/session/{session_id}", tags=["Admin"])
async def delete_session_admin(
    session_id: str,
    knox_id: str = Depends(require_admin)
):
    """관리자용 세션 삭제 (하드 삭제)"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
        cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
        conn.commit()
    
    logger.info(f"Session hard deleted by admin: {session_id}")
    return {"status": "success", "message": f"Session {session_id} deleted"}

# ==========================================
# Static Files & Main
# ==========================================

@app.get("/")
async def root():
    return FileResponse(Path(__file__).parent / "index_db.html")

@app.get("/admin")
async def admin_page():
    return FileResponse(Path(__file__).parent / "admin.html")

@app.get("/main/api/me")
async def get_current_user():
    """현재 사용자 정보 (SSO 연동 시 확장)"""
    return {
        "knox_id": "test_user",
        "is_admin": True,
        "name": "Test User"
    }

app.mount("/static", StaticFiles(directory=Path(__file__).parent), name="static")

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    init_db_pool()
    logger.info("ADK Web UI Server started")

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 실행"""
    if db_pool:
        db_pool.closeall()
    logger.info("ADK Web UI Server stopped")

if __name__ == "__main__":
    print("=" * 70)
    print("ADK Web UI Server - Phase 2 Complete")
    print("=" * 70)
    print(f"\nDatabase: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"\nAPI Documentation: http://localhost:{settings.PORT}/docs")
    print(f"Admin Panel: http://localhost:{settings.PORT}/admin")
    print("\nFeatures:")
    print("  ✅ 설정 외부화 (config.py)")
    print("  ✅ 구조화된 로깅")
    print("  ✅ OpenAPI/Swagger 문서화")
    print("  ✅ 메시지 검색")
    print("  ✅ 세션 이름 변경")
    print("  ✅ 파일 첨부 (Mock)")
    print("  ✅ 메시지 복사/삭제")
    print("  ✅ 무한 스크롤 (페이지네이션)")
    print("  ✅ 대화 내역 내보내기")
    print("  ✅ 읽음 확인")
    print("=" * 70)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL)