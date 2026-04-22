"""
ADK Web UI Server - Alternative to ADK Web CLI
FastAPI 기반 웹 서버로 ADK Agent를 시각적으로 관리
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

# Import agents
sys.path.insert(0, str(Path(__file__).parent.parent / 'adk_agents'))
from chatbot_company_adk import root_agent as company_agent
from chatbot_hr_adk import root_agent as hr_agent
from chatbot_tech_adk import root_agent as tech_agent

app = FastAPI(title="ADK Web UI Server", version="1.0.0")

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

# Session service
session_service = InMemorySessionService()

# Runner cache
runners = {}

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
    """Run an agent with a message"""
    
    if request.agent not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")
    
    agent = AGENTS[request.agent]
    
    # Get or create session
    try:
        session = await session_service.get_session(
            app_name=request.agent,
            user_id="web_user",
            session_id=request.session_id
        )
        if not session:
            session = await session_service.create_session(
                app_name=request.agent,
                user_id="web_user",
                session_id=request.session_id
            )
    except Exception as e:
        # Session might not exist, create new one
        session = await session_service.create_session(
            app_name=request.agent,
            user_id="web_user",
            session_id=request.session_id
        )
    
    # Get or create runner
    if request.agent not in runners:
        runners[request.agent] = Runner(
            agent=agent,
            app_name=request.agent,
            session_service=session_service
        )
    
    runner = runners[request.agent]
    
    # Collect response
    response_parts = []
    
    try:
        async for event in runner.run_async(
            user_id="web_user",
            session_id=request.session_id,
            new_message=request.message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_parts.append(part.text)
        
        full_response = " ".join(response_parts) if response_parts else "No response"
        
        return ChatResponse(
            response=full_response,
            session_id=request.session_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files
app.mount("/", StaticFiles(directory=Path(__file__).parent, html=True), name="static")

if __name__ == "__main__":
    print("=" * 60)
    print("ADK Web UI Server")
    print("=" * 60)
    print(f"\nServing {len(AGENTS)} agents:")
    for name in AGENTS:
        print(f"  - {name}")
    print("\nAccess at: http://localhost:8084")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8084)
