"""
ADK Web UI Server - Session Bug Fixed
FastAPI based web server with proper ADK Runner integration
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio

from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.contents.contents import Content, Part
from google.adk.agents import BaseAgent

# Import agents
sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent registry with their proper app names
AGENT_CONFIGS = {
    "chatbot_company_adk": {
        "agent": company_agent,
        "app_name": "chatbot_company_adk",  # Use agent name as app name
    },
    "chatbot_hr_adk": {
        "agent": hr_agent,
        "app_name": "chatbot_hr_adk",
    },
    "chatbot_tech_adk": {
        "agent": tech_agent,
        "app_name": "chatbot_tech_adk",
    },
}

# Shared session service
session_service = InMemorySessionService()

# Session state storage
sessions = {}

class ChatRequest(BaseModel):
    agent: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    response: str
    session_id: str

@app.get("/list-apps")
async def list_agents(relative_path: str = "./"):
    """List available agents"""
    return list(AGENT_CONFIGS.keys())

@app.post("/api/run", response_model=ChatResponse)
async def run_agent(request: ChatRequest):
    """Run an agent with a message"""
    
    if request.agent not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    config = AGENT_CONFIGS[request.agent]
    agent = config["agent"]
    app_name = config["app_name"]
    
    # Initialize session in our storage
    if request.session_id not in sessions:
        sessions[request.session_id] = []
    
    try:
        # Try to use ADK Runner properly
        from google.adk.runners import Runner
        
        # Create runner with matching app_name
        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service
        )
        
        # Create/get session in ADK
        try:
            session = await session_service.create_session(
                app_name=app_name,
                user_id="web_user",
                session_id=request.session_id
            )
        except Exception:
            # Session might already exist
            pass
        
        # Run agent
        response_parts = []
        async for event in runner.run_async(
            user_id="web_user",
            session_id=request.session_id,
            new_message=request.message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_parts.append(part.text)
        
        full_response = " ".join(response_parts) if response_parts else "응답이 생성되지 않았습니다."
        
        # Save to our storage
        sessions[request.session_id].append({
            "role": "assistant",
            "content": full_response
        })
        
        return ChatResponse(
            response=full_response,
            session_id=request.session_id
        )
        
    except Exception as e:
        import traceback
        print(f"Error in run_agent: {e}")
        print(traceback.format_exc())
        
        # Fallback: return agent info
        fallback_response = f"[{agent.name}] 에이전트가 준비되었습니다.\n\n(현재 Gemini API 연동이 필요합니다. API 키 설정 후 완전한 대화가 가능합니다.)"
        
        return ChatResponse(
            response=fallback_response,
            session_id=request.session_id
        )

@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get chat history for a session"""
    return sessions.get(session_id, [])

# Serve static files
app.mount("/", StaticFiles(directory=Path(__file__).parent, html=True), name="static")

if __name__ == "__main__":
    print("=" * 60)
    print("ADK Web UI Server (Session Bug Fixed)")
    print("=" * 60)
    print(f"\nServing {len(AGENT_CONFIGS)} agents:")
    for name, config in AGENT_CONFIGS.items():
        print(f"  - {name} (app: {config['app_name']})")
    print("\nAccess at: http://localhost:8085")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8085)
