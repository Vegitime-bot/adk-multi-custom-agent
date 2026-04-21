from __future__ import annotations
"""
roles/agent_handler.py - Agent 모드 처리
- 대화 메모리를 적극 활용
- 검색 컨텍스트를 포함한 풍부한 응답 생성
- SSE 스트리밍 지원
"""
from typing import Generator

from backend.core.models import ExecutionContext, Message
from backend.llm.client import build_messages, chat_once, stream_chat
from backend.retrieval.ingestion_client import IngestionClient, format_context
from backend.roles.base import BaseRoleHandler


class AgentHandler(BaseRoleHandler):
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

    def run(self, context: ExecutionContext, user_message: str) -> str:
        retrieved_context = self._retrieve(context, user_message)
        messages = build_messages(
            system_prompt=context.chatbot_def.system_prompt,
            history=context.history,
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
            history=context.history,
            user_message=user_message,
            context=retrieved_context,
        )
        yield from stream_chat(context.chatbot_def, messages)
