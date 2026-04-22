"""
ADK Web UI Server - Mock Mode (No API Calls)
Agent 출력 → 클릭 → 명령 전송 → 위임 체인 확인
실제 Google API 호출 없이 내부 로직만 테스트
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
from typing import List, Dict
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server - Mock Mode", version="6.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# 위임 로직 시뮬레이션
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

def check_delegation(current_agent: str, message: str) -> tuple:
    """
    메시지 내용에 따라 위임 대상 결정
    Returns: (target_agent, reason)
    """
    keywords = KEYWORD_DELEGATION.get(current_agent, {})
    for keyword, target in keywords.items():
        if keyword in message:
            return target, f"키워드 '{keyword}' 감지"
    return current_agent, "현재 Agent가 처리"

def generate_mock_response(agent_id: str, message: str, delegation_chain: List[str]) -> str:
    """
    Mock 응답 생성 (실제 API 호출 없이)
    """
    config = AGENT_CONFIGS[agent_id]
    agent_name = config["display_name"]
    
    response = f"""[{agent_name}] 응답 (Mock Mode)

📨 수신 메시지: "{message}"

🔍 Agent 정보:
  - ID: {agent_id}
  - 이름: {agent_name}
  - 레벨: {config['level']}
  - 하위 Agent: {', '.join(config['sub_agents']) if config['sub_agents'] else '없음'}

🔗 위임 체인: {' → '.join(delegation_chain)}

📝 처리 결과: 현재 Mock 모드로 실행되었습니다. 실제 LLM 응답은 API 키가 필요합니다.
"""
    return response

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

@app.post("/api/run", response_model=ChatResponse)
async def run_agent(request: ChatRequest):
    """Agent 실행 (Mock Mode)"""
    log_debug("=" * 70)
    log_debug(f"RUN AGENT (MOCK): {request.agent}")
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
    
    # 위임 체크
    delegated_agent, reason = check_delegation(request.agent, request.message)
    log_debug(f"  Delegation check: {reason}")
    
    # 위임 체인 업데이트
    if delegated_agent != request.agent:
        sessions[request.session_id]["delegation_chain"].append(delegated_agent)
        log_debug(f"  → Delegated to: {delegated_agent}")
    
    delegation_chain = sessions[request.session_id]["delegation_chain"]
    
    # 사용자 메시지 저장
    sessions[request.session_id]["history"].append({
        "role": "user",
        "content": request.message,
        "agent": request.agent,
        "timestamp": datetime.now().isoformat()
    })
    
    # Mock 응답 생성
    log_debug(f"  Generating mock response...")
    response_text = generate_mock_response(delegated_agent, request.message, delegation_chain)
    
    # 응답 저장
    sessions[request.session_id]["history"].append({
        "role": "assistant",
        "content": response_text,
        "agent": delegated_agent,
        "timestamp": datetime.now().isoformat()
    })
    
    log_debug(f"  Final delegation chain: {' → '.join(delegation_chain)}")
    log_debug(f"  Response length: {len(response_text)} chars")
    log_debug("=" * 70)
    
    return ChatResponse(
        response=response_text,
        session_id=request.session_id,
        agent_used=delegated_agent,
        delegation_chain=delegation_chain,
        debug_info={
            "original_agent": request.agent,
            "delegated_agent": delegated_agent,
            "delegation_reason": reason,
            "agent_level": config["level"],
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
    print("ADK Web UI Server - MOCK MODE (No API Calls)")
    print("=" * 70)
    print(f"\nAgent 목록:")
    for agent_id, config in AGENT_CONFIGS.items():
        print(f"  [{config['level']}] {agent_id}: {config['display_name']}")
        print(f"      하위: {config.get('sub_agents', [])}")
    print("\n위임 규칙:")
    for agent, keywords in KEYWORD_DELEGATION.items():
        print(f"  {agent}: {list(keywords.keys())} → 위임")
    print("\n엔드포인트:")
    print("  GET  /list-apps")
    print("  GET  /api/agents/detail")
    print("  POST /api/run  (Mock 응답)")
    print("  GET  /api/debug/logs")
    print("\n접속: http://localhost:8090")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
