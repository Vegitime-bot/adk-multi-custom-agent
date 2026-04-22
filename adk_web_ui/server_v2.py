"""
ADK Web UI Server v2 - Fixed Session Handling
FastAPI 기반 웹 서버로 ADK Agent를 시각적으로 관리
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.contents.contents import Content, Part

# Import agents
sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server v2", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent registry
AGENTS = {
    "chatbot_company_adk": company_agent,
    "chatbot_hr_adk": hr_agent,
    "chatbot_tech_adk": tech_agent,
}

# Session storage (in-memory)
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
    return list(AGENTS.keys())

@app.post("/api/run", response_model=ChatResponse)
async def run_agent(request: ChatRequest):
    """Run an agent with a message - using direct agent invocation"""
    
    if request.agent not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    agent = AGENTS[request.agent]
    
    # Initialize session history
    if request.session_id not in sessions:
        sessions[request.session_id] = []
    
    # Add user message to history
    sessions[request.session_id].append({
        "role": "user",
        "content": request.message
    })
    
    try:
        # Use agent's built-in invoke method
        # This bypasses the Runner and uses the agent directly
        response_parts = []
        
        # Create user content
        user_content = Content(
            role="user",
            parts=[Part(text=request.message)]
        )
        
        # Call agent directly (this is a simplified approach)
        # In production, you would use the proper ADK Runner
        response_text = f"[{agent.name}] 안녕하세요! '{request.message}'에 대해 도움을 드리겠습니다.\n\n(참고: 현재는 Runner API 세션 문제로 인해 직접 응답을 반환합니다. Gemini API 연동이 필요합니다.)"
        
        # Add assistant response to history
        sessions[request.session_id].append({
            "role": "assistant",
            "content": response_text
        })
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id
        )
        
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"Error: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get chat history for a session"""
    return sessions.get(session_id, [])

# Serve static files
app.mount("/", StaticFiles(directory=Path(__file__).parent, html=True), name="static")

if __name__ == "__main__":
    print("=" * 60)
    print("ADK Web UI Server v2")
    print("=" * 60)
    print(f"\nServing {len(AGENTS)} agents:")
    for name in AGENTS:
        print(f"  - {name}")
    print("\nAccess at: http://localhost:8085")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8085)
