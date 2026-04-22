"""
ADK Web UI Server - SQLite Mode (로컬 테스트용)
채팅 데이터 DB 저장 + 세션별 기록 관리 + 초기화 기능
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import sqlite3

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server - SQLite Mode", version="8.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite 경로
DB_PATH = Path(__file__).parent.parent / "adk_chat.db"

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
        "인사": "chatbot_hr_adk",
        "휴가": "chatbot_hr_adk",
        "급여": "chatbot_hr_adk",
        "복지": "chatbot_hr_adk",
        "기술": "chatbot_tech_adk",
        "개발": "chatbot_tech_adk",
        "시스템": "chatbot_tech_adk",
        "버그": "chatbot_tech_adk",
    }
}

def init_db():
    """SQLite DB 초기화"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            initial_agent TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            agent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS delegation_chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            agent_id TEXT,
            order_index INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ SQLite DB initialized: {DB_PATH}")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

def check_delegation(current_agent: str, message: str) -> tuple:
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    for keyword, target in keywords.items():
        if keyword in message:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"

def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    config = AGENT_CONFIGS[agent_id]
    agent_name = config["display_name"]
    
    return f"""[{agent_name}] 응답

📨 수신 메시지: "{message}"

🔍 Agent: {agent_id}
🔗 위임 체인: {' → '.join(delegation_chain)}
"""

def save_message(session_id: str, role: str, content: str, agent_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (session_id, role, content, agent_id)
        VALUES (?, ?, ?, ?)
    ''', (session_id, role, content, agent_id))
    conn.commit()
    conn.close()

def save_session(session_id: str, initial_agent: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO sessions (session_id, updated_at, initial_agent, is_active)
        VALUES (?, CURRENT_TIMESTAMP, ?, 1)
    ''', (session_id, initial_agent))
    conn.commit()
    conn.close()

def save_delegation_chain(session_id: str, chain: List[str]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
    for idx, agent_id in enumerate(chain):
        cursor.execute('''
            INSERT INTO delegation_chains (session_id, agent_id, order_index)
            VALUES (?, ?, ?)
        ''', (session_id, agent_id, idx))
    conn.commit()
    conn.close()

def get_session_history(session_id: str) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, content, agent_id, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_delegation_chain(session_id: str) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT agent_id FROM delegation_chains
        WHERE session_id = ?
        ORDER BY order_index ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['agent_id'] for row in rows]

def get_all_sessions() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.session_id, s.created_at, s.updated_at, s.initial_agent, s.is_active,
               COUNT(m.id) as message_count
        FROM sessions s
        LEFT JOIN messages m ON s.session_id = m.session_id
        WHERE s.is_active = 1
        GROUP BY s.session_id
        ORDER BY s.updated_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def reset_session(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
    cursor.execute('UPDATE sessions SET is_active = 0 WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/list-apps")
async def list_agents(relative_path: str = "./"):
    return list(AGENT_CONFIGS.keys())

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
async def run_agent(request: ChatRequest):
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    
    save_session(request.session_id, request.agent)
    
    delegated_agent, reason = check_delegation(request.agent, request.message)
    
    if request.agent == delegated_agent:
        chain = [request.agent]
    else:
        chain = [request.agent, delegated_agent]
    
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
            "agent_level": config["level"],
            "saved_to_db": True
        }
    )

@app.post("/api/session/reset")
async def reset_session_endpoint(request: ResetRequest):
    reset_session(request.session_id)
    return {
        "status": "success",
        "message": f"Session '{request.session_id}' has been reset",
        "session_id": request.session_id
    }

@app.get("/api/session/{session_id}/history")
async def get_session_history_endpoint(session_id: str):
    history = get_session_history(session_id)
    chain = get_delegation_chain(session_id)
    return {
        "session_id": session_id,
        "history": history,
        "delegation_chain": chain
    }

@app.get("/api/sessions")
async def list_sessions():
    sessions = get_all_sessions()
    result = []
    for session in sessions:
        chain = get_delegation_chain(session['session_id'])
        session['delegation_chain'] = chain
        result.append(session)
    return {"sessions": result}

@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = ?', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Session '{session_id}' deleted"}

# 정적 파일
@app.get("/")
async def root():
    return FileResponse(Path(__file__).parent / "index_db.html")

app.mount("/static", StaticFiles(directory=Path(__file__).parent), name="static")

if __name__ == "__main__":
    print("=" * 70)
    print("ADK Web UI Server - SQLITE MODE (Local Test)")
    print("=" * 70)
    print(f"\nDatabase: {DB_PATH}")
    print(f"\n접속: http://localhost:8092")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8092, log_level="info")
