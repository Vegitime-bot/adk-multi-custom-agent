from __future__ import annotations
"""
executors/tool_executor.py - Tool 모드 Executor
함수처럼 실행: 상태 비저장, 단발성 호출
"""
from typing import Generator

from backend.core.models import ChatbotDef
from backend.executors.base_executor import BaseExecutor
from backend.retrieval.ingestion_client import IngestionClient


class ToolExecutor(BaseExecutor):
    """
    Tool 모드 Executor
    - 메모리 없음 (히스토리 유지 안 함)
    - 단발성 호출 (함수처럼)
    - 외부 오케스트레이터 연동에 적합
    """

    def __init__(self, chatbot_def: ChatbotDef, ingestion_client: IngestionClient):
        super().__init__(chatbot_def, ingestion_client)

    def execute(
        self,
        message: str,
        session_id: str | None = None,
    ) -> Generator[str, None, None]:
        """
        Tool 모드 실행
        
        Args:
            message: 사용자 입력
            session_id: 선택적 (Tool은 세션 무관)
            
        Yields:
            LLM 응답 청크
        """
        # 1. RAG 검색 (DB 스코프 적용)
        context = self._retrieve(
            query=message,
            db_ids=self.chatbot_def.retrieval.db_ids,
        )

        # 2. 메시지 구성 (히스토리 없음 - Tool 특성)
        messages = self._build_messages(
            system_prompt=self.chatbot_def.system_prompt,
            user_message=message,
            context=context,
        )

        # 3. LLM 스트리밍 호출
        yield from self._stream_chat(messages)

        # 4. 메모리 저장 없음 (Tool 특성)
