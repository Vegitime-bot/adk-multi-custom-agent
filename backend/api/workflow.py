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
    overall_status: str


@router.post("/run", response_model=WorkflowResponse)
async def run_workflow(request: WorkflowRequest, r: Request):
    """
    3단계 Agent 워크플로우 실행
    
    - Phase 1: Architecture (설계)
    - Phase 2: Implementation (구현)
    - Phase 3: Validation (검증)
    """
    auth.get_current_user(r)
    
    try:
        orchestrator = get_orchestrator()
        
        phases = []
        async for result in orchestrator.run_workflow(
            task=request.task,
            context=request.context,
            session_id=request.session_id
        ):
            phases.append(WorkflowPhaseResponse(
                phase=result.phase,
                agent_name=result.agent_name,
                output=result.output,
                status=result.status,
                duration_ms=result.duration_ms
            ))
        
        # 전체 상태 결정
        overall_status = "success"
        if any(p.status == "error" for p in phases):
            overall_status = "partial_failure"
        if all(p.status == "error" for p in phases):
            overall_status = "failure"
        
        return WorkflowResponse(
            workflow_id=request.session_id or "auto-generated",
            phases=phases,
            overall_status=overall_status
        )
        
    except Exception as e:
        logger.error(f"[WorkflowAPI] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run/stream")
async def run_workflow_stream(request: WorkflowRequest, r: Request):
    """3단계 워크플로우 스트리밍 실행"""
    auth.get_current_user(r)
    
    async def generate():
        try:
            orchestrator = get_orchestrator()
            
            async for result in orchestrator.run_workflow(
                task=request.task,
                context=request.context,
                session_id=request.session_id
            ):
                import json
                yield f"data: {json.dumps({
                    'phase': result.phase,
                    'agent': result.agent_name,
                    'status': result.status,
                    'duration_ms': result.duration_ms,
                    'output_preview': result.output[:500] if result.output else ''
                })}\n\n"
            
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
def list_agents(r: Request):
    """사용 가능한 워크플로우 Agent 목록"""
    auth.get_current_user(r)
    
    return {
        "agents": [
            {
                "name": "architecture_agent",
                "description": "시스템 아키텍처 설계 전문가",
                "phase": 1
            },
            {
                "name": "implementation_agent",
                "description": "소프트웨어 구현 및 개발 전문가",
                "phase": 2
            },
            {
                "name": "validation_agent",
                "description": "테스트 및 검증 전문가",
                "phase": 3
            }
        ]
    }
