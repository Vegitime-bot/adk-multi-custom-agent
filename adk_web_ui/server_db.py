"""
ADK Web UI Server - PostgreSQL Mode
채팅 데이터 DB 저장 + 세션별 기록 관리 + 초기화 기능
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="ADK Web UI Server - PostgreSQL Mode", version="8.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PostgreSQL 설정 (환경 변수에서 읽기)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'adk_chat')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')

def get_db_connection():
    """PostgreSQL 연결 반환"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
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

# 위임 로직
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
    """메시지 내용에 따라 위임 대상 결정"""
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    for keyword, target in keywords.items():
        if keyword in message:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"

def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    """Mock 응답 생성"""
    config = AGENT_CONFIGS[agent_id]
    agent_name = config["display_name"]
    
    response = f"""[{agent_name}] 응답 (PostgreSQL Mode)

📨 수신 메시지: "{message}"

🔍 Agent 정보:
  - ID: {agent_id}
  - 이름: {agent_name}
  - 레벨: {config['level']}
  - 하위 Agent: {', '.join(config['sub_agents']) if config['sub_agents'] else '없음'}

🔗 위임 체인: {' → '.join(delegation_chain)}

📝 처리 결과: PostgreSQL에 기록되었습니다.
"""
    return response

def save_message(session_id: str, role: str, content: str, agent_id: str):
    """메시지 저장 (PostgreSQL)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (session_id, role, content, agent_id)
        VALUES (%s, %s, %s, %s)
    ''', (session_id, role, content, agent_id))
    conn.commit()
    conn.close()

def save_session(session_id: str, initial_agent: str):
    """세션 저장 (없으면 생성, 있으면 업데이트)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sessions (session_id, initial_agent, is_active)
        VALUES (%s, %s, %s)
        ON CONFLICT (session_id) DO UPDATE SET
        updated_at = CURRENT_TIMESTAMP,
        is_active = 1
    ''', (session_id, initial_agent, 1))
    conn.commit()
    conn.close()

def save_delegation_chain(session_id: str, chain: List[str]):
    """위임 체인 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 기존 체인 삭제
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    # 새 체인 저장
    for idx, agent_id in enumerate(chain):
        cursor.execute('''
            INSERT INTO delegation_chains (session_id, agent_id, order_index)
            VALUES (%s, %s, %s)
        ''', (session_id, agent_id, idx))
    conn.commit()
    conn.close()

def get_session_history(session_id: str) -> List[Dict]:
    """세션 히스토리 조회"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT id, session_id, role, content, agent_id, created_at
        FROM messages
        WHERE session_id = %s
        ORDER BY created_at ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_delegation_chain(session_id: str) -> List[str]:
    """위임 체인 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT agent_id FROM delegation_chains
        WHERE session_id = %s
        ORDER BY order_index ASC
    ''', (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_all_sessions() -> List[Dict]:
    """모든 세션 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
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
    """세션 초기화 (메시지 및 위임 체인 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 메시지 삭제
    cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
    # 위임 체인 삭제
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    # 세션 비활성화
    cursor.execute('UPDATE sessions SET is_active = 0 WHERE session_id = %s', (session_id,))
    conn.commit()
    conn.close()

@app.get("/list-apps")
async def list_agents(relative_path: str = "./"):
    """Agent 목록 출력"""
    return list(AGENT_CONFIGS.keys())

@app.get("/api/agents/detail")
async def get_agents_detail():
    """상세 Agent 정보"""
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
    """Agent 실행 + DB 저장"""
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    
    # 세션 저장 (초기 Agent 설정)
    save_session(request.session_id, request.agent)
    
    # 위임 체크
    delegated_agent, reason = check_delegation(request.agent, request.message)
    
    # 위임 체인 생성
    if request.agent == delegated_agent:
        chain = [request.agent]
    else:
        chain = [request.agent, delegated_agent]
    
    # 위임 체인 저장
    save_delegation_chain(request.session_id, chain)
    
    # 사용자 메시지 저장
    save_message(request.session_id, "user", request.message, request.agent)
    
    # Mock 응답 생성
    response_text = generate_mock_response(delegated_agent, request.message, chain)
    
    # 어시스턴트 응답 저장
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
    """세션 초기화"""
    reset_session(request.session_id)
    return {
        "status": "success",
        "message": f"Session '{request.session_id}' has been reset",
        "session_id": request.session_id
    }

@app.get("/api/session/{session_id}/history")
async def get_session_history_endpoint(session_id: str):
    """세션 히스토리 조회 (DB)"""
    history = get_session_history(session_id)
    chain = get_delegation_chain(session_id)
    return {
        "session_id": session_id,
        "history": history,
        "delegation_chain": chain
    }

@app.get("/api/sessions")
async def list_sessions():
    """모든 세션 목록 (DB)"""
    sessions = get_all_sessions()
    # 각 세션에 위임 체인 추가
    result = []
    for session in sessions:
        chain = get_delegation_chain(session['session_id'])
        session['delegation_chain'] = chain
        result.append(session)
    return {"sessions": result}

@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """세션 삭제 (완전 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM delegation_chains WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Session '{session_id}' deleted"}

# 정적 파일
app.mount("/", StaticFiles(directory=Path(__file__).parent, html=True), name="static")

if __name__ == "__main__":
    print("=" * 70)
    print("ADK Web UI Server - POSTGRESQL MODE")
    print("=" * 70)
    print(f"\nDatabase: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"\nAgent 목록:")
    for agent_id, config in AGENT_CONFIGS.items():
        print(f"  [{config['level']}] {agent_id}: {config['display_name']}")
    print("\n엔드포인트:")
    print("  GET  /list-apps")
    print("  GET  /api/agents/detail")
    print("  POST /api/run              - 메시지 전송 및 저장")
    print("  GET  /api/sessions           - 세션 목록")
    print("  GET  /api/session/{id}/history")
    print("  POST /api/session/reset      - 세션 초기화")
    print("  DELETE /api/session/{id}   - 세션 삭제")
    print("\n접속: http://localhost:8091")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=8091, log_level="info")
