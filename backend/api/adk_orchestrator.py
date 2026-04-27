"""
backend/api/adk_orchestrator.py - 3단계 Agent 워크플로우 오케스트레이터
Architecture → Implementation → Validation
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, AsyncGenerator, List
from dataclasses import dataclass

# ADK Agents 디렉토리 추가
ADK_AGENTS_DIR = Path(__file__).parent.parent.parent / "adk_agents"
sys.path.insert(0, str(ADK_AGENTS_DIR))

from backend.debug_logger import logger
from backend.config import settings

try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types
    ADK_AVAILABLE = True
except ImportError as e:
    logger.error(f"ADK import failed: {e}")
    ADK_AVAILABLE = False


@dataclass
class WorkflowResult:
    """워크플로우 실행 결과"""
    phase: str
    agent_name: str
    output: str
    status: str  # "success", "error", "pending"
    duration_ms: int
    artifacts: List[str]  # 생성된 파일/코드 목록


class ADKWorkflowOrchestrator:
    """
    3단계 Agent 워크플로우 오케스트레이터
    
    Phase 1: Architecture - 시스템 설계
    Phase 2: Implementation - 코드 구현  
    Phase 3: Validation - 테스트 및 검증
    """
    
    def __init__(self):
        if not ADK_AVAILABLE:
            raise RuntimeError("ADK not available")
        
        self.session_service = InMemorySessionService()
        self._agents: dict[str, Agent] = {}
        
        # 3개 Agent 로드
        self._load_agents()
        logger.info("[ADKWorkflowOrchestrator] Initialized with 3 agents")
    
    def _load_agents(self):
        """3개 Agent 로드"""
        agent_modules = [
            ("architecture_agent", "architecture_agent"),
            ("implementation_agent", "implementation_agent"),
            ("validation_agent", "validation_agent"),
        ]
        
        for module_name, agent_key in agent_modules:
            try:
                module = __import__(module_name, fromlist=['agent'])
                self._agents[agent_key] = module.agent
                logger.info(f"[ADKWorkflowOrchestrator] Loaded {agent_key}")
            except Exception as e:
                logger.error(f"[ADKWorkflowOrchestrator] Failed to load {agent_key}: {e}")
    
    async def run_workflow(
        self,
        task: str,
        context: dict = None,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[WorkflowResult, None]:
        """
        3단계 워크플로우 실행
        
        Args:
            task: 수행할 작업 설명
            context: 추가 컨텍스트
            session_id: 세션 ID (재시도용)
            
        Yields:
            WorkflowResult: 각 단계 결과
        """
        import time
        
        session_id = session_id or f"workflow-{int(time.time() * 1000)}"
        user_id = "orchestrator"
        
        # Phase 1: Architecture
        logger.info(f"[ADKWorkflow] Phase 1: Architecture - {task}")
        start_time = time.time()
        
        arch_result = await self._run_agent(
            agent_key="architecture_agent",
            user_id=user_id,
            session_id=f"{session_id}-arch",
            message=f"다음 작업의 아키텍처를 설계해주세요:\n\n{task}\n\n컨텍스트: {context or {}}"
        )
        
        yield WorkflowResult(
            phase="architecture",
            agent_name="architecture_agent",
            output=arch_result,
            status="success" if arch_result else "error",
            duration_ms=int((time.time() - start_time) * 1000),
            artifacts=[]
        )
        
        # Phase 2: Implementation
        logger.info(f"[ADKWorkflow] Phase 2: Implementation")
        start_time = time.time()
        
        impl_result = await self._run_agent(
            agent_key="implementation_agent",
            user_id=user_id,
            session_id=f"{session_id}-impl",
            message=f"다음 아키텍처를 기반으로 구현해주세요:\n\n{arch_result}\n\n원본 작업: {task}"
        )
        
        yield WorkflowResult(
            phase="implementation",
            agent_name="implementation_agent",
            output=impl_result,
            status="success" if impl_result else "error",
            duration_ms=int((time.time() - start_time) * 1000),
            artifacts=[]
        )
        
        # Phase 3: Validation
        logger.info(f"[ADKWorkflow] Phase 3: Validation")
        start_time = time.time()
        
        val_result = await self._run_agent(
            agent_key="validation_agent",
            user_id=user_id,
            session_id=f"{session_id}-val",
            message=f"다음 구현을 검증해주세요:\n\n{impl_result}\n\n원본 아키텍처: {arch_result}\n\n원본 작업: {task}"
        )
        
        yield WorkflowResult(
            phase="validation",
            agent_name="validation_agent",
            output=val_result,
            status="success" if val_result else "error",
            duration_ms=int((time.time() - start_time) * 1000),
            artifacts=[]
        )
        
        logger.info(f"[ADKWorkflow] Workflow completed: {session_id}")
    
    async def _run_agent(
        self,
        agent_key: str,
        user_id: str,
        session_id: str,
        message: str
    ) -> str:
        """단일 Agent 실행"""
        agent = self._agents.get(agent_key)
        if not agent:
            logger.error(f"[ADKWorkflow] Agent not found: {agent_key}")
            return ""
        
        try:
            # 세션 먼저 생성
            from google.adk.sessions import Session
            session = self.session_service.create_session(
                app_name="adk-workflow",
                user_id=user_id,
                session_id=session_id
            )
            
            runner = Runner(
                agent=agent,
                app_name="adk-workflow",
                session_service=self.session_service
            )
            
            content = types.Content(role='user', parts=[types.Part(text=message)])
            
            full_response = []
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            full_response.append(part.text)
            
            return "".join(full_response)
            
        except Exception as e:
            logger.error(f"[ADKWorkflow] Agent execution failed: {e}", exc_info=True)
            return ""


# 전역 오케스트레이터
_orchestrator: Optional[ADKWorkflowOrchestrator] = None


def get_orchestrator() -> ADKWorkflowOrchestrator:
    """오케스트레이터 싱글톤 반환"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ADKWorkflowOrchestrator()
    return _orchestrator
