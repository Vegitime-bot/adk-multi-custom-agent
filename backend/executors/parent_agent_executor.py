from __future__ import annotations
"""
executors/parent_agent_executor.py - 상위 Agent Executor (위임 기능 포함)

⚠️ DEPRECATED: 이 모듈은 하위 호환성을 위해 유지됩니다.
새로운 구현은 hierarchical_agent_executor.py를 사용하세요.

변경사항:
- v3: 다중 하위 Agent 병렬 실행 및 응답 종합
- v4: 3-tier hierarchy 지원 (hierarchical_agent_executor로 위임)
"""
from typing import Generator

from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
from backend.core.models import ChatbotDef
from backend.managers.memory_manager import MemoryManager
from backend.retrieval.ingestion_client import IngestionClient


class ParentAgentExecutor(HierarchicalAgentExecutor):
    """
    상위 Agent Executor (레거시 호환용)
    
    이 클래스는 기존 코드와의 하위 호환성을 위해 유지됩니다.
    실제 구현은 HierarchicalAgentExecutor를 상속받아 사용합니다.
    
    Migration Guide:
    - 기존: from backend.executors.parent_agent_executor import ParentAgentExecutor
    - 신규: from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
    """

    def __init__(
        self,
        chatbot_def: ChatbotDef,
        ingestion_client: IngestionClient,
        memory_manager: MemoryManager,
        chatbot_manager=None,
    ):
        # HierarchicalAgentExecutor 초기화 (3-tier 지원)
        super().__init__(
            chatbot_def=chatbot_def,
            ingestion_client=ingestion_client,
            memory_manager=memory_manager,
            chatbot_manager=chatbot_manager,
            accumulated_context="",
            delegation_depth=0,
        )
        
        # 상위 위임은 기존 동작과 동일하게 유지 (sub_chatbots 우선)
        # enable_parent_delegation을 False로 설정하면 기존 2-level 동작
        self.enable_parent_delegation = chatbot_def.policy.get(
            'enable_parent_delegation', False
        )

    def execute(
        self,
        message: str,
        session_id: str,
    ) -> Generator[str, None, None]:
        """
        상위 Agent 실행 + 위임 로직
        
        레거시 동작:
        - 기본적으로 sub_chatbots로만 위임 (2-level)
        - enable_parent_delegation=True 시 3-tier hierarchy 활성화
        """
        # 부모 클래스의 execute 호출
        yield from super().execute(message, session_id)


# 레거시 import 지원
__all__ = ['ParentAgentExecutor']
