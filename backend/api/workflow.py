"""backend/api/workflow.py - 3단계 Agent 워크플로우 API"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from backend.api.middleware import auth_middleware as auth
from backend.api.adk_orchestrator import get_orchestrator, WorkflowResult
from backend.debug_logger import logger

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowRequest(BaseModel):
    task: str
    context: Optional[dict] = None
    session_id: Optional[str] = None


class WorkflowPhaseResponse(BaseModel):
    phase: str
    agent_name: str
    output: str
    status: str
    duration_ms: int


class WorkflowResponse(BaseModel):
    workflow_id: str
    phases: List[WorkflowPhaseResponse]
    status: str


@router.post("/run")
async def run_workflow(request: WorkflowRequest):
    """
    3단계 워크플로우 실행 (비동기)
    
    Architecture → Implementation → Validation
    """
    try:
        orch = get_orchestrator()
        
        results = []
        async for result in orch.run_workflow(
            task=request.task,
            context=request.context,
            session_id=request.session_id
        ):
            results.append(result)
        
        return {
            "workflow_id": request.session_id or "sync-workflow",
            "phases": [
                {
                    "phase": r.phase,
                    "agent_name": r.agent_name,
                    "output": r.output,
                    "status": r.status,
                    "duration_ms": r.duration_ms
                }
                for r in results
            ],
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"[WorkflowAPI] Error: {e}")
        raise HTTPException(500, f"Workflow error: {str(e)}")


@router.post("/run/stream")
async def run_workflow_stream(request: WorkflowRequest):
    """
    3단계 워크플로우 실행 (SSE 스트리밍)
    
    실시간으로 각 단계 결과를 전송
    """
    async def generate():
        try:
            orch = get_orchestrator()
            
            async for result in orch.run_workflow(
                task=request.task,
                context=request.context,
                session_id=request.session_id
            ):
                import json
                data = {
                    'phase': result.phase,
                    'agent': result.agent_name,
                    'status': result.status,
                    'duration_ms': result.duration_ms,
                    'output_preview': result.output[:500] if result.output else ''
                }
                yield f"data: {json.dumps(data)}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"[WorkflowAPI] Stream error: {e}")
            yield f"data: {{'error': '{str(e)}'}}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )


@router.get("/agents")
def list_workflow_agents():
    """워크플로우 Agent 목록"""
    return {
        "agents": [
            {
                "id": "architecture_agent",
                "name": "Architecture Agent",
                "description": "시스템 설계 및 아키텍처 담당"
            },
            {
                "id": "implementation_agent",
                "name": "Implementation Agent",
                "description": "코드 구현 담당"
            },
            {
                "id": "validation_agent",
                "name": "Validation Agent",
                "description": "테스트 및 검증 담당"
            }
        ]
    }
