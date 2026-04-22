"""
ADK Web UI Server - Agent Direct Invoke (No Runner)
Agent 출력 → 클릭 → 명령 전송 → 위임 확인
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import uvicorn
import asyncio
import json

sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent
from google.genai.types import Content, Part

app = FastAPI(title="ADK Web UI Server - Debug v2", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 설정
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

# 세션 저장소
sessions = {}
debug_logs = []

def log_debug(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] {message}"
    debug_logs.append(log_entry)
    print(log_entry)
    if len(debug_logs) > 1000:
        debug_logs.pop(0)

class ChatRequest(BaseModel):
    agent: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    response: str
    session_id: str
    agent_used: str
    delegation_chain: List[str]
    debug_info: Dict

@app.get("/list-apps")
async def list_agents(relative_path: str = "./"):
    """Agent 목록 출력"""
    log_debug(f"list-apps called: {len(AGENT_CONFIGS)} agents")
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

async def invoke_agent_with_runner(agent, message: str, session_id: str, app_name: str) -> str:
    """
    Runner를 사용하여 Agent 실행 (Content 객체 사용)
    """
    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    
    log_debug(f"    Creating Runner for {agent.name}...")
    session_service = InMemorySessionService()
    
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service
    )
    log_debug(f"    Runner created")
    
    # Content 객체 생성
    user_content = Content(
        role="user",
        parts=[Part(text=message)]
    )
    log_debug(f"    Content created: role={user_content.role}")
    
    # 세션 생성
    try:
        await session_service.create_session(
            app_name=app_name,
            user_id="web_user",
            session_id=session_id
        )
        log_debug(f"    Session created")
    except Exception:
        log_debug(f"    Session may already exist")
    
    # Agent 실행
    response_parts = []
    event_count = 0
    
    try:
        async for event in runner.run_async(
            user_id="web_user",
            session_id=session_id,
            new_message=user_content
        ):
            event_count += 1
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts') and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_parts.append(part.text)
        
        log_debug(f"    Events: {event_count}, Response parts: {len(response_parts)}")
        
        if response_parts:
            return " ".join(response_parts)
        else:
            return f"[{agent.name}] 응답이 생성되지 않았습니다. (이벤트: {event_count})"
            
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        log_debug(f"    Runner error: {str(e)}")
        return f"[{agent.name}] Runner 오류: {str(e)[:200]}"

async def invoke_agent_direct(agent, message: str, session_history: list) -> str:
    """
    Agent를 직접 invoke (Runner 사용)
    """
    log_debug(f"    Invoking agent: {agent.name}")
    log_debug(f"    Message: {message[:50]}...")
    
    # Agent 설정
    instruction = getattr(agent, 'instruction', None)
    if instruction:
        log_debug(f"    Instruction: {instruction[:80]}...")
    
    tools = getattr(agent, 'tools', None)
    if tools:
        log_debug(f"    Tools: {len(tools) if tools else 0}")
    
    sub_agents = getattr(agent, 'sub_agents', None)
    if sub_agents:
        log_debug(f"    Sub-agents: {len(sub_agents)}")
    
    # Runner 사용
    return await invoke_agent_with_runner(agent, message, "session_" + str(id(agent)), agent.name)

@app.post("/api/run", response_model=ChatResponse)
async def run_agent(request: ChatRequest):
    """Agent 실행 + 위임 확인"""
    log_debug("=" * 70)
    log_debug(f"RUN AGENT: {request.agent}")
    log_debug(f"  Message: {request.message}")
    log_debug(f"  Session: {request.session_id}")
    
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    agent = config["agent"]
    
    # 세션 초기화
    if request.session_id not in sessions:
        sessions[request.session_id] = {
            "history": [],
            "delegation_chain": [request.agent]
        }
        log_debug(f"  New session created")
    else:
        sessions[request.session_id]["delegation_chain"].append(request.agent)
        log_debug(f"  Session updated, delegation chain: {sessions[request.session_id]['delegation_chain']}")
    
    # 사용자 메시지 저장
    sessions[request.session_id]["history"].append({
        "role": "user",
        "content": request.message,
        "agent": request.agent,
        "timestamp": datetime.now().isoformat()
    })
    
    # Agent 직접 invoke
    log_debug(f"  Calling invoke_agent_direct...")
    response_text = await invoke_agent_direct(
        agent, 
        request.message, 
        sessions[request.session_id]["history"]
    )
    
    # 위임 체인
    delegation_chain = sessions[request.session_id].get("delegation_chain", [request.agent])
    log_debug(f"  Delegation chain: {' -> '.join(delegation_chain)}")
    
    # 응답 저장
    sessions[request.session_id]["history"].append({
        "role": "assistant",
        "content": response_text,
        "agent": request.agent,
        "timestamp": datetime.now().isoformat()
    })
    
    log_debug(f"  Response length: {len(response_text)} chars")
    log_debug("=" * 70)
    
    return ChatResponse(
        response=response_text,
        session_id=request.session_id,
        agent_used=request.agent,
        delegation_chain=delegation_chain,
        debug_info={
            "agent_name": agent.name,
            "agent_level": config["level"],
            "has_sub_agents": len(config.get("sub_agents", [])) > 0,
            "message_count": len(sessions[request.session_id]["history"])
        }
    )

@app.get("/api/debug/logs")
async def get_debug_logs(lines: int = 100):
    """최근 디버그 로그 확인"""
    return {"logs": debug_logs[-lines:]}

@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str):
    """세션 히스토리 확인"""
    session = sessions.get(session_id, {"history": [], "delegation_chain": []})
    return {
        "session_id": session_id,
        "history": session.get("history", []),
        "delegation_chain": session.get("delegation_chain", [])
    }

@app.get("/api/sessions")
async def list_sessions():
    """모든 세션 목록"""
    return {
        "sessions": [
            {
                "id": sid,
                "message_count": len(s.get("history", [])),
                "delegation_chain": s.get("delegation_chain", [])
            }
            for sid, s in sessions.items()
        ]
    }

# 정적 파일
app.mount("/", StaticFiles(directory=Path(__file__).parent, html=True), name="static")

if __name__ == "__main__":
    print("=" * 70)
    print("ADK Web UI Server - AGENT DIRECT INVOKE MODE")
    print("=" * 70)
    print(f"\nAgent 목록:")
    for agent_id, config in AGENT_CONFIGS.items():
        agent = config["agent"]
        print(f"  [{config['level']}] {agent_id}")
        print(f"      이름: {agent.name}")
        print(f"      설명: {config['description']}")
        print(f"      instruction: {getattr(agent, 'instruction', 'None')[:60]}...")
        print(f"      하위: {config.get('sub_agents', [])}")
        print()
    print("\n엔드포인트:")
    print("  GET  /list-apps")
    print("  GET  /api/agents/detail")
    print("  POST /api/run")
    print("  GET  /api/debug/logs")
    print("  GET  /api/sessions")
    print("\n접속: http://localhost:8088")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=8088, log_level="info")
