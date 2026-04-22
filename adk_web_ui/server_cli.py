"""
ADK Web UI Server - Using adk run CLI (No API Key Required)
Agent 출력 → 클릭 → 명령 전송 → 위임 확인
"""

import sys
import os
import subprocess
import json
import tempfile
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

app = FastAPI(title="ADK Web UI Server - CLI Mode", version="5.0.0")

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

def run_adk_cli(agent_id: str, message: str) -> str:
    """
    adk run CLI를 서브프로세스로 실행
    """
    agent_path = f"/Users/vegitime/.openclaw/workspace/projects/adk-multi-custom-agent/adk_agents/{agent_id}"
    
    # CLI 입력용 임시 파일 생성
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        session_file = f.name
    
    try:
        # adk run 명령어 실행
        # --save_session 옵션으로 세션 저장
        cmd = [
            "adk", "run",
            "--save_session",
            "--session_id", f"cli_session_{agent_id}",
            agent_path
        ]
        
        log_debug(f"    Running CLI: {' '.join(cmd)}")
        log_debug(f"    Input message: {message[:50]}...")
        
        # 프로세스 실행 (입력 전달)
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd="/Users/vegitime/.openclaw/workspace/projects/adk-multi-custom-agent"
        )
        
        # 메시지 입력 및 종료 명령
        input_data = f"{message}\n\nexit\n"
        stdout, stderr = process.communicate(input=input_data, timeout=30)
        
        log_debug(f"    CLI exit code: {process.returncode}")
        
        # 출력 파싱
        if stdout:
            # 마지막 응답 부분 추출
            lines = stdout.strip().split('\n')
            # "User: " 다음에 오는 "Assistant: " 부분 찾기
            response_lines = []
            capture = False
            for line in lines:
                if line.startswith("User:"):
                    capture = True
                    response_lines = []
                elif line.startswith("Assistant:") and capture:
                    response_lines.append(line.replace("Assistant:", "").strip())
                elif capture and response_lines and not line.startswith("User:"):
                    if line and not line.startswith("INFO:"):
                        response_lines.append(line.strip())
            
            if response_lines:
                return " ".join(response_lines)
            else:
                # 전체 출력에서 응답 추출 시도
                return f"[CLI 출력]\n{stdout[:500]}"
        
        if stderr:
            return f"[CLI 에러] {stderr[:300]}"
        
        return "(CLI 응답 없음)"
        
    except subprocess.TimeoutExpired:
        process.kill()
        return "(CLI 타임아웃)"
    except Exception as e:
        return f"[CLI 실행 오류] {str(e)}"
    finally:
        # 임시 파일 정리
        try:
            os.unlink(session_file)
        except:
            pass

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
    """Agent 실행 (CLI 방식)"""
    log_debug("=" * 70)
    log_debug(f"RUN AGENT (CLI): {request.agent}")
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
    
    # 사용자 메시지 저장
    sessions[request.session_id]["history"].append({
        "role": "user",
        "content": request.message,
        "agent": request.agent,
        "timestamp": datetime.now().isoformat()
    })
    
    # CLI로 Agent 실행
    log_debug(f"  Calling adk run CLI...")
    response_text = run_adk_cli(request.agent, request.message)
    
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
    
    log_debug(f"  Response: {response_text[:200]}...")
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
            "method": "adk_cli"
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
    print("ADK Web UI Server - ADK RUN CLI MODE")
    print("=" * 70)
    print(f"\nAgent 목록:")
    for agent_id, config in AGENT_CONFIGS.items():
        print(f"  [{config['level']}] {agent_id}: {config['display_name']}")
    print("\n엔드포인트:")
    print("  GET  /list-apps")
    print("  GET  /api/agents/detail")
    print("  POST /api/run  (uses 'adk run' CLI)")
    print("  GET  /api/debug/logs")
    print("\n접속: http://localhost:8089")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=8089, log_level="info")
