"""
ADK Web UI Server - PostgreSQL Mode v2
Knox ID 기반 저장 + 관리자 기능
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server - PostgreSQL v2", version="9.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PostgreSQL 설정
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'adk_chat')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')

# 관리자 목록 (환경 변수로 설정)
ADMIN_KNOX_IDS = os.getenv('ADMIN_KNOX_IDS', '').split(',')

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )

AGENT_CONFIGS = {
    "chatbot_company_adk": {
        "agent": company_agent,
        "app_name": "chatbot_company_adk",
        "display_name": "회사 전체 지원",
        "description": "모든 사내 문의 처리",
        "level": 0,
        "sub_agents": ["chatbot_hr_adk", "chatbot_tech_adk"]
    },
    "chatbot_hr_adk": {
        "agent": hr_agent,
        "app_name": "chatbot_hr_adk",
        "display_name": "인사지원",
        "description": "인사 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": []
    },
    "chatbot_tech_adk": {
        "agent": tech_agent,
        "app_name": "chatbot_tech_adk",
        "display_name": "기술지원",
        "description": "기술 관련 문의",
        "level": 1,
        "parent": "chatbot_company_adk",
        "sub_agents": []
    },
}

KEYWORD_DELEGATION = {
    "chatbot_company_adk": {
        "인사": "chatbot_hr_adk", "휴가": "chatbot_hr_adk",
        "급여": "chatbot_hr_adk", "복지": "chatbot_hr_adk",
        "기술": "chatbot_tech_adk", "개발": "chatbot_tech_adk",
        "시스템": "chatbot_tech_adk", "버그": "chatbot_tech_adk",
    }
}

# Pydantic 모델
class ChatRequest(BaseModel):
    agent: str
    message: str
    session_id: str

class ResetRequest(BaseModel):
    session_id: str

class ChatResponse(BaseModel):
    response: str
    session_id: str
    agent_used: str
    delegation_chain: List[str]
    debug_info: Dict

# 관리자 체크 함수
def is_admin(knox_id: str) -> bool:
    """관리자 여부 확인"""
    if not knox_id:
        return False
    # DB에서도 확인
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM admin_users WHERE knox_id = %s', (knox_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None or knox_id in ADMIN_KNOX_IDS

def check_delegation(current_agent: str, message: str) -> tuple:
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    for keyword, target in keywords.items():
        if keyword in message:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"

def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    config = AGENT_CONFIGS[agent_id]
    return f"[{config['display_name']}] 응답\n\n📨 {message}\n🔗 {' → '.join(delegation_chain)}"

def save_message(session_id: str, role: str, content: str, agent_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO messages (session_id, role, content, agent_id) VALUES (%s, %s, %s, %s)',
        (session_id, role, content, agent_id)
    )
    conn.commit()
    conn.close()

def save_session(session_id: str, knox_id: str, initial_agent: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sessions (session_id, knox_id, initial_agent, is_active)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
    ''', (session_id, knox_id, initial_agent))
    conn.commit()
    conn.close()

def save_delegation_chain(session_id: str, chain: List[str]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    for idx, agent_id in enumerate(chain):
        cursor.execute(
            'INSERT INTO delegation_chains (session_id, agent_id, order_index) VALUES (%s, %s, %s)',
            (session_id, agent_id, idx)
        )
    conn.commit()
    conn.close()

def get_session_history(session_id: str, knox_id: str) -> List[Dict]:
    """knox_id로 권한 체크 후 히스토리 조회"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    # 본인 세션만 조회 가능
    cursor.execute('''
        SELECT m.role, m.content, m.agent_id, m.created_at
        FROM messages m
        JOIN sessions s ON m.session_id = s.session_id
        WHERE m.session_id = %s AND s.knox_id = %s
        ORDER BY m.created_at ASC
    ''', (session_id, knox_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_sessions(knox_id: str) -> List[Dict]:
    """사용자별 세션 목록"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT s.session_id, s.created_at, s.updated_at, s.initial_agent, s.is_active,
               COUNT(m.id) as message_count
        FROM sessions s
        LEFT JOIN messages m ON s.session_id = m.session_id
        WHERE s.knox_id = %s AND s.is_active = 1
        GROUP BY s.session_id
        ORDER BY s.updated_at DESC
    ''', (knox_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def reset_session(session_id: str, knox_id: str):
    """본인 세션만 초기화 가능"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # knox_id 확인
    cursor.execute('SELECT 1 FROM sessions WHERE session_id = %s AND knox_id = %s', 
                   (session_id, knox_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    
    cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    conn.commit()
    conn.close()

# ============ 사용자 API ============

@app.get("/api/agents/detail")
async def get_agents_detail():
    return [
        {
            "id": agent_id,
            "name": config["display_name"],
            "description": config["description"],
            "level": config["level"],
            "app_name": config["app_name"],
            "sub_agents": config.get("sub_agents", []),
            "parent": config.get("parent")
        }
        for agent_id, config in AGENT_CONFIGS.items()
    ]

@app.post("/api/run", response_model=ChatResponse)
async def run_agent(
    request: ChatRequest,
    x_knox_id: Optional[str] = Header(None)
):
    if not x_knox_id:
        raise HTTPException(status_code=401, detail="Knox ID required")
    
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    save_session(request.session_id, x_knox_id, request.agent)
    
    delegated_agent, reason = check_delegation(request.agent, request.message)
    chain = [request.agent] if request.agent == delegated_agent else [request.agent, delegated_agent]
    
    save_delegation_chain(request.session_id, chain)
    save_message(request.session_id, "user", request.message, request.agent)
    
    response_text = generate_mock_response(delegated_agent, request.message, chain)
    save_message(request.session_id, "assistant", response_text, delegated_agent)
    
    return ChatResponse(
        response=response_text,
        session_id=request.session_id,
        agent_used=delegated_agent,
        delegation_chain=chain,
        debug_info={
            "original_agent": request.agent,
            "delegated_agent": delegated_agent,
            "delegation_reason": reason,
            "agent_level": config["level"]
        }
    )

@app.post("/api/session/reset")
async def reset_session_endpoint(
    request: ResetRequest,
    x_knox_id: Optional[str] = Header(None)
):
    if not x_knox_id:
        raise HTTPException(status_code=401, detail="Knox ID required")
    
    reset_session(request.session_id, x_knox_id)
    return {"status": "success", "message": "Session reset"}

@app.get("/api/session/{session_id}/history")
async def get_session_history_endpoint(
    session_id: str,
    x_knox_id: Optional[str] = Header(None)
):
    if not x_knox_id:
        raise HTTPException(status_code=401, detail="Knox ID required")
    
    history = get_session_history(session_id, x_knox_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT agent_id FROM delegation_chains
        WHERE session_id = %s ORDER BY order_index ASC
    ''', (session_id,))
    chain = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return {"session_id": session_id, "history": history, "delegation_chain": chain}

@app.get("/api/sessions")
async def list_sessions(x_knox_id: Optional[str] = Header(None)):
    """본인 세션만 조회"""
    if not x_knox_id:
        raise HTTPException(status_code=401, detail="Knox ID required")
    
    sessions = get_user_sessions(x_knox_id)
    for session in sessions:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT agent_id FROM delegation_chains
            WHERE session_id = %s ORDER BY order_index ASC
        ''', (session['session_id'],))
        session['delegation_chain'] = [row[0] for row in cursor.fetchall()]
        conn.close()
    
    return {"sessions": sessions}

# ============ 관리자 API ============

@app.get("/admin/stats")
async def get_admin_stats(x_knox_id: Optional[str] = Header(None)):
    """관리자용 통계"""
    if not x_knox_id or not is_admin(x_knox_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 전체 통계
    cursor.execute('SELECT COUNT(*) as total_sessions FROM sessions')
    total_sessions = cursor.fetchone()['total_sessions']
    
    cursor.execute('SELECT COUNT(*) as total_messages FROM messages')
    total_messages = cursor.fetchone()['total_messages']
    
    cursor.execute('SELECT COUNT(DISTINCT knox_id) as unique_users FROM sessions')
    unique_users = cursor.fetchone()['unique_users']
    
    # 사용자별 세션 수
    cursor.execute('''
        SELECT knox_id, COUNT(*) as session_count
        FROM sessions GROUP BY knox_id ORDER BY session_count DESC LIMIT 10
    ''')
    top_users = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "unique_users": unique_users,
        "top_users": top_users
    }

@app.get("/admin/sessions")
async def get_all_sessions_admin(
    x_knox_id: Optional[str] = Header(None),
    limit: int = 100
):
    """관리자용 전체 세션 조회"""
    if not x_knox_id or not is_admin(x_knox_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT s.*, COUNT(m.id) as message_count
        FROM sessions s
        LEFT JOIN messages m ON s.session_id = m.session_id
        GROUP BY s.session_id
        ORDER BY s.updated_at DESC
        LIMIT %s
    ''', (limit,))
    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"sessions": sessions}

@app.delete("/admin/session/{session_id}")
async def delete_session_admin(
    session_id: str,
    x_knox_id: Optional[str] = Header(None)
):
    """관리자용 세션 삭제"""
    if not x_knox_id or not is_admin(x_knox_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"Session {session_id} deleted"}

# 정적 파일
@app.get("/")
async def root():
    return FileResponse(Path(__file__).parent / "index_db.html")

@app.get("/admin")
async def admin_page():
    return FileResponse(Path(__file__).parent / "admin.html")

app.mount("/static", StaticFiles(directory=Path(__file__).parent), name="static")

if __name__ == "__main__":
    print("=" * 70)
    print("ADK Web UI Server - POSTGRESQL v2 (Knox ID + Admin)")
    print("=" * 70)
    print(f"\nDatabase: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"\n엔드포인트:")
    print("  사용자 API:")
    print("    GET  /api/sessions           - 본인 세션 목록 (x-knox-id 필요)")
    print("    GET  /api/session/{id}/history - 세션 히스토리")
    print("    POST /api/run                - 메시지 전송")
    print("    POST /api/session/reset      - 세션 초기화")
    print("  관리자 API:")
    print("    GET  /admin/stats            - 전체 통계")
    print("    GET  /admin/sessions         - 전체 세션 조회")
    print("    DELETE /admin/session/{id}   - 세션 삭제")
    print("\n관리자 Knox ID:", ADMIN_KNOX_IDS)
    print("\n접속: http://localhost:8093")
    print("관리자: http://localhost:8093/admin")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8093, log_level="info")
