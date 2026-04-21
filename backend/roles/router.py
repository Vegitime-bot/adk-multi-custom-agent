from __future__ import annotations
"""
roles/router.py - Agent Router
실행 컨텍스트의 effective_role에 따라 적절한 핸들러를 선택한다.
"""
from backend.core.models import ExecutionRole
from backend.retrieval.ingestion_client import IngestionClient
from backend.roles.agent_handler import AgentHandler
from backend.roles.base import BaseRoleHandler
from backend.roles.tool_handler import ToolHandler


class RoleRouter:
    def __init__(self, ingestion_client: IngestionClient):
        self._agent = AgentHandler(ingestion_client)
        self._tool  = ToolHandler(ingestion_client)

    def resolve(self, role: ExecutionRole) -> BaseRoleHandler:
        if role == ExecutionRole.AGENT:
            return self._agent
        return self._tool
