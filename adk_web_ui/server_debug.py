"""
ADK Web UI Server - Full Debugging Version
Agent 출력 → 클릭 → 명령 전송 → 위임 확인
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import uvicorn
import asyncio
import json

from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.runners import Runner
from google.adk.contents import Content, Part

sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server - Debug", version="3.0.0")

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

session_service = InMemorySessionService()
sessions = {}
debug_logs = []

def log_debug(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] {message}"
    debug_logs.append(log_entry)
    print(log_entry)
    # 최근 1000개만 유지
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

@app.get("/")
async def root():
    log_debug("Root endpoint accessed")
    return {"status": "ADK Debug Server Running", "agents": list(AGENT_CONFIGS.keys())}

@app.get("/list-apps")
async def list_agents(relative_path: str = "./"):
    """Agent 목록 출력"""
    log_debug(f"list-apps called with relative_path={relative_path}")
    
    agent_list = []
    for agent_id, config in AGENT_CONFIGS.items():
        agent_info = {
            "id": agent_id,
            "name": config["display_name"],
            "description": config["description"],
            "level": config["level"],
            "app_name": config["app_name"],
            "sub_agents": config.get("sub_agents", []),
            "parent": config.get("parent")
        }
        agent_list.append(agent_info)
        log_debug(f"  Agent: {agent_id} -> {config['display_name']} (Level {config['level']})")
    
    log_debug(f"Total agents: {len(agent_list)}")
    return [a["id"] for a in agent_list]

@app.get("/api/agents/detail")
async def get_agents_detail():
    """상세 Agent 정보"""
    log_debug("Getting detailed agent info")
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
    """Agent 실행 + 위임 확인"""
    log_debug("=" * 60)
    log_debug(f"RUN AGENT CALLED")
    log_debug(f"  Input Agent: {request.agent}")
    log_debug(f"  Message: {request.message}")
    log_debug(f"  Session ID: {request.session_id}")
    
    if request.agent not in AGENT_CONFIGS:
        log_debug(f"ERROR: Agent '{request.agent}' not found!")
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    agent = config["agent"]
    app_name = config["app_name"]
    
    log_debug(f"  Selected Agent: {agent.name}")
    log_debug(f"  App Name: {app_name}")
    log_debug(f"  Agent Level: {config['level']}")
    log_debug(f"  Sub-agents: {config.get('sub_agents', [])}")
    
    # 세션 초기화
    if request.session_id not in sessions:
        sessions[request.session_id] = {
            "history": [],
            "delegation_chain": [request.agent]
        }
        log_debug(f"  New session created: {request.session_id}")
    else:
        log_debug(f"  Existing session: {request.session_id}")
        sessions[request.session_id]["delegation_chain"].append(request.agent)
    
    # 사용자 메시지 저장
    sessions[request.session_id]["history"].append({
        "role": "user",
        "content": request.message,
        "agent": request.agent,
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        # Runner 생성
        log_debug(f"  Creating Runner...")
        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service
        )
        log_debug(f"  Runner created successfully")
        
        # ADK 세션 생성
        log_debug(f"  Creating ADK session...")
        try:
            await session_service.create_session(
                app_name=app_name,
                user_id="web_user",
                session_id=request.session_id
            )
            log_debug(f"  ADK session created")
        except Exception as e:
            log_debug(f"  Session might exist: {e}")
        
        # Run agent with Content object (not str)
        log_debug(f"  Creating Content object...")
        user_content = Content(
            role="user",
            parts=[Part(text=request.message)]
        )
        log_debug(f"  Content created: role={user_content.role}")
        
        response_parts = []
        event_count = 0
        
        async for event in runner.run_async(
            user_id="web_user",
            session_id=request.session_id,
            new_message=user_content  # Content 객체로 전달
        ):
            event_count += 1
            log_debug(f"    Event {event_count}: {type(event).__name__}")
            
            if event.content and event.content.parts:
                for i, part in enumerate(event.content.parts):
                    if hasattr(part, 'text') and part.text:
                        log_debug(f"    Part {i}: {part.text[:80]}...")
                        response_parts.append(part.text)
        
        log_debug(f"  Total events: {event_count}")
        log_debug(f"  Response parts: {len(response_parts)}")
        
        full_response = " ".join(response_parts) if response_parts else "(응답 없음)"
        
        # 위임 체인 확인
        delegation_chain = sessions[request.session_id].get("delegation_chain", [request.agent])
        log_debug(f"  Delegation chain: {' -> '.join(delegation_chain)}")
        
        # 응답 저장
        sessions[request.session_id]["history"].append({
            "role": "assistant",
            "content": full_response,
            "agent": request.agent,
            "timestamp": datetime.now().isoformat()
        })
        
        log_debug(f"  Final response length: {len(full_response)} chars")
        log_debug("=" * 60)
        
        return ChatResponse(
            response=full_response,
            session_id=request.session_id,
            agent_used=request.agent,
            delegation_chain=delegation_chain,
            debug_info={
                "events_processed": event_count,
                "response_parts": len(response_parts),
                "app_name": app_name,
                "agent_level": config["level"]
            }
        )
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        log_debug(f"ERROR: {error_msg}")
        log_debug(f"Stack trace:\n{stack_trace}")
        
        # 에러 응답
        return ChatResponse(
            response=f"[오류] {error_msg}\n\n스택 트레이스:\n{stack_trace[:500]}",
            session_id=request.session_id,
            agent_used=request.agent,
            delegation_chain=[request.agent],
            debug_info={
                "error": error_msg,
                "stack_trace": stack_trace[:1000]
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
    print("ADK Web UI Server - FULL DEBUG MODE")
    print("=" * 70)
    print(f"\nAgent 목록:")
    for agent_id, config in AGENT_CONFIGS.items():
        print(f"  [{config['level']}] {agent_id}")
        print(f"      이름: {config['display_name']}")
        print(f"      설명: {config['description']}")
        print(f"      하위: {config.get('sub_agents', [])}")
        print()
    print("\n엔드포인트:")
    print("  GET  /list-apps           - Agent 목록")
    print("  GET  /api/agents/detail   - 상세 Agent 정보")
    print("  POST /api/run             - Agent 실행 (핵심)")
    print("  GET  /api/debug/logs      - 디버그 로그")
    print("  GET  /api/sessions        - 세션 목록")
    print("\n접속: http://localhost:8086")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=8086, log_level="info")
