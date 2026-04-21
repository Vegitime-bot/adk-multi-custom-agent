from __future__ import annotations
"""
roles/tool_handler.py - Tool 모드 처리
- 명확한 입력/출력 계약
- 메모리 사용 여부를 명시적으로 제어 (chatbot_def.memory.enabled)
- 외부 오케스트레이터가 예측 가능하게 사용할 수 있도록 설계
"""
from typing import Generator

from backend.core.models import ExecutionContext
from backend.llm.client import build_messages, chat_once, stream_chat
from backend.retrieval.ingestion_client import IngestionClient, format_context
from backend.roles.base import BaseRoleHandler


class ToolHandler(BaseRoleHandler):
    def __init__(self, ingestion_client: IngestionClient):
        self._ingestion = ingestion_client

    def _retrieve(self, context: ExecutionContext, query: str) -> str:
        if not context.authorized_db_ids:
            return ""
        results = self._ingestion.search(
            db_ids=context.authorized_db_ids,
            query=query,
            k=context.chatbot_def.retrieval.k,
            filter_metadata=context.chatbot_def.retrieval.filter_metadata or None,
        )
        return format_context(results)

    def _get_history(self, context: ExecutionContext):
        """Tool 모드에서는 memory.enabled가 false이면 히스토리를 비운다."""
        if context.chatbot_def.memory.enabled:
            return context.history
        return []

    def run(self, context: ExecutionContext, user_message: str) -> str:
        retrieved_context = self._retrieve(context, user_message)
        messages = build_messages(
            system_prompt=context.chatbot_def.system_prompt,
            history=self._get_history(context),
            user_message=user_message,
            context=retrieved_context,
        )
        return chat_once(context.chatbot_def, messages)

    def stream(
        self, context: ExecutionContext, user_message: str
    ) -> Generator[str, None, None]:
        retrieved_context = self._retrieve(context, user_message)
        messages = build_messages(
            system_prompt=context.chatbot_def.system_prompt,
            history=self._get_history(context),
            user_message=user_message,
            context=retrieved_context,
        )
        yield from stream_chat(context.chatbot_def, messages)
