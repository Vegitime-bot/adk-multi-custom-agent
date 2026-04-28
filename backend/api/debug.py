"""
backend/api/debug.py - ADK Debug API

ADK 내부 상태를 확인할 수 있는 디버그 엔드포인트
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.debug_logger import logger

router = APIRouter(prefix="/debug", tags=["debug"])


# ── 스키마 ───────────────────────────────────────────────────────
class AgentInfo(BaseModel):
    name: str
    description: str
    tool_count: int
    tools: List[str]


class AgentsResponse(BaseModel):
    root_agent: Optional[AgentInfo]
    sub_agents: List[AgentInfo]
    total_agents: int


class SessionEvent(BaseModel):
    role: str
    content: str
    timestamp: Optional[str]
    author: Optional[str]


class SessionDebugResponse(BaseModel):
    session_id: str
    chatbot_id: Optional[str]
    user_knox_id: Optional[str]
    event_count: int
    events: List[SessionEvent]


class ToolCallInfo(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str]
    timestamp: str


class ExecutionTrace(BaseModel):
    chatbot_id: str
    message: str
    timestamp: str
    tool_calls: List[ToolCallInfo]
    final_response: str
    execution_time_ms: int


# ── 헬퍼 함수 ──────────────────────────────────────────────────
def _get_router():
    """DelegationRouter 인스턴스 반환"""
    try:
        from adk_agents.delegation_router_agent import get_router
        router = get_router()
        # root_agent 속성이 있는지 확인
        if not hasattr(router, 'root_agent'):
            return None
        return router
    except Exception as e:
        logger.error(f"[DebugAPI] Failed to get router: {e}")
        return None


def _get_session_wrapper():
    """ADKSessionWrapper 인스턴스 반환"""
    try:
        from backend.adk.adk_session_wrapper import get_session_wrapper
        return get_session_wrapper()
    except Exception as e:
        logger.error(f"[DebugAPI] Failed to get session wrapper: {e}")
        return None


# ── API 엔드포인트 ──────────────────────────────────────────────
@router.get("/health")
async def debug_health():
    """디버그 API 상태 확인"""
    return {
        "status": "ok",
        "debug_api": "available",
        "endpoints": [
            "/debug/agents",
            "/debug/sessions/{session_id}",
            "/debug/run"
        ]
    }


@router.get("/agents")
async def list_agents():
    """등록된 ADK Agents 목록 조회"""
    try:
        from adk_agents.sub_agent_factory import SubAgentFactory
        import os
        import json
        
        factory = SubAgentFactory()
        chatbots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'chatbots')
        
        agents = []
        if os.path.exists(chatbots_dir):
            for filename in sorted(os.listdir(chatbots_dir)):
                if filename.endswith('.json'):
                    filepath = os.path.join(chatbots_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        chatbot_def = json.load(f)
                    
                    chatbot_id = chatbot_def.get('id', '')
                    if chatbot_id:
                        try:
                            agent = factory.create_agent(chatbot_def)
                            agents.append({
                                "id": chatbot_id,
                                "name": chatbot_def.get('name', chatbot_id),
                                "description": chatbot_def.get('description', ''),
                                "tools": [t.name for t in getattr(agent, 'tools', [])],
                                "has_sub_chatbots": bool(chatbot_def.get('sub_chatbots'))
                            })
                        except Exception as e:
                            logger.warning(f"[DebugAPI] Failed to create agent for {chatbot_id}: {e}")
        
        return {
            "total_agents": len(agents),
            "agents": agents
        }
    except Exception as e:
        logger.error(f"[DebugAPI] Failed to list agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=SessionDebugResponse)
async def get_session_events(session_id: str):
    """
    ADK 세션 이벤트 조회
    
    특정 세션의 대화 히스토리와 내부 이벤트를 반환합니다.
    """
    try:
        wrapper = _get_session_wrapper()
        if not wrapper:
            raise HTTPException(status_code=503, detail="ADK Session not available")
        
        # 세션 조회
        session = wrapper.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # ADK 내부 세션 접근
        events = []
        try:
            adk_sessions = getattr(wrapper._session_service, '_sessions', {})
            for key, adk_session in adk_sessions.items():
                if adk_session.session_id == session_id:
                    if hasattr(adk_session, 'events'):
                        for event in adk_session.events:
                            events.append(SessionEvent(
                                role=getattr(event, 'role', 'unknown'),
                                content=getattr(event, 'content', '')[:500],  # 500자 제한
                                timestamp=str(getattr(event, 'timestamp', '')),
                                author=getattr(event, 'author', None)
                            ))
                    break
        except Exception as e:
            logger.warning(f"[DebugAPI] Failed to get ADK events: {e}")
        
        return SessionDebugResponse(
            session_id=session_id,
            chatbot_id=getattr(session, 'chatbot_id', None),
            user_knox_id=getattr(session, 'user_knox_id', None),
            event_count=len(events),
            events=events
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DebugAPI] Failed to get session events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def debug_run(request: Request):
    """
    디버그 실행
    
    ADK Agent를 직접 실행하고 상세 실행 결과를 반환합니다.
    """
    try:
        import time
        from backend.api.chat_service_v2 import get_chat_service_v2
        
        body = await request.json()
        chatbot_id = body.get("chatbot_id")
        message = body.get("message")
        session_id = body.get("session_id", f"debug-{int(time.time())}")
        
        if not chatbot_id or not message:
            raise HTTPException(status_code=400, detail="chatbot_id and message are required")
        
        service = get_chat_service_v2()
        
        start_time = time.time()
        chunks = []
        tool_calls = []
        
        async for chunk in service.chat_stream(
            chatbot_id=chatbot_id,
            message=message,
            session_id=session_id
        ):
            chunks.append(chunk)
            
            # Tool 호출 감지
            if "[도구 호출:" in chunk:
                tool_name = chunk.split("[도구 호출:")[1].split("]")[0].strip()
                tool_calls.append(ToolCallInfo(
                    tool_name=tool_name,
                    arguments={},
                    result=None,
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S")
                ))
        
        execution_time = int((time.time() - start_time) * 1000)
        
        return ExecutionTrace(
            chatbot_id=chatbot_id,
            message=message,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            tool_calls=tool_calls,
            final_response="".join(chunks),
            execution_time_ms=execution_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DebugAPI] Debug run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_logs(limit: int = 100):
    """
    최근 서버 로그 조회
    """
    try:
        import os
        from pathlib import Path
        
        log_file = Path("server_live.log")
        if not log_file.exists():
            return {"logs": [], "total": 0}
        
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # 최근 N줄
        recent_lines = lines[-limit:]
        
        return {
            "logs": [line.strip() for line in recent_lines],
            "total": len(recent_lines)
        }
    except Exception as e:
        logger.error(f"[DebugAPI] Failed to get logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))