from __future__ import annotations
"""
executors/agent_executor.py - Agent 모드 Executor
대화 주체처럼 실행: 메모리 유지, 대화형
"""
from typing import Generator

from backend.core.models import ChatbotDef, Message
from backend.executors.base_executor import BaseExecutor
from backend.managers.memory_manager import MemoryManager
from backend.retrieval.ingestion_client import IngestionClient


class AgentExecutor(BaseExecutor):
    """
    Agent 모드 Executor
    - 메모리 유지 (히스토리 저장)
    - 대화형 (세션 기반)
    - 사용자와 지속적 대화에 적합
    """

    def __init__(
        self,
        chatbot_def: ChatbotDef,
        ingestion_client: IngestionClient,
        memory_manager: MemoryManager,
    ):
        super().__init__(chatbot_def, ingestion_client)
        self.memory = memory_manager

    def execute(
        self,
        message: str,
        session_id: str,
    ) -> Generator[str, None, None]:
        """
        Agent 모드 실행
        
        Args:
            message: 사용자 입력
            session_id: 필수 (Agent는 세션 기반)
            
        Yields:
            LLM 응답 청크
        """
        # DEBUG: 실행 정보 로깅
        print(f"[DEBUG AgentExecutor] ========== START ==========")
        print(f"[DEBUG AgentExecutor] chatbot_id: {self.chatbot_def.id}")
        print(f"[DEBUG AgentExecutor] session_id: {session_id}")
        print(f"[DEBUG AgentExecutor] db_ids: {self.chatbot_def.retrieval.db_ids}")
        print(f"[DEBUG AgentExecutor] query: {message[:100]}...")
        
        # 1. 메모리에서 히스토리 복원
        history = self.memory.get_history(self.chatbot_def.id, session_id)
        print(f"[DEBUG AgentExecutor] history loaded: {len(history)} messages")

        # 2. 히스토리 압축 및 검색 쿼리 확장
        compacted = self._compact_history(history)
        if compacted:
            print(f"[DEBUG AgentExecutor] compacted history:\n{compacted[:200]}...")
        
        enhanced_query = self._build_contextual_query(compacted, message)
        if enhanced_query != message:
            print(f"[DEBUG AgentExecutor] query enhanced: '{message[:50]}...' -> '{enhanced_query[:100]}...'")

        # 3. RAG 검색 (확장된 쿼리 사용)
        print(f"[DEBUG AgentExecutor] calling _retrieve with query: {enhanced_query[:50]}...")
        context = self._retrieve(
            query=enhanced_query,
            db_ids=self.chatbot_def.retrieval.db_ids,
        )
        print(f"[DEBUG AgentExecutor] _retrieve returned context length: {len(context)}")

        # 2.5 Confidence 체크
        confidence = self._calculate_confidence(context, message)
        print(f"[DEBUG AgentExecutor] confidence: {confidence}, context length: {len(context)}")
        
        # DEBUG: 임시로 fallback 제거 (검색 테스트용)
        # 실제 운영 시에는 아래 로직 활성화 필요
        """
        # 정책/규정 관련 키워드 체크
        policy_keywords = ['규정', '정책', '제도', '지침', '방침', '법규']
        is_policy_question = any(kw in message for kw in policy_keywords)
        
        if confidence < 20 or (is_policy_question and confidence < 50):
            fallback_msg = (
                "죄송합니다. 해당 내용은 제 전문 분야가 아닙니다. "
                "인사정책 전문 챗봇에게 문의해 주세요."
            )
            yield fallback_msg
            self.memory.append_pair(
                chatbot_id=self.chatbot_def.id,
                session_id=session_id,
                user_content=message,
                assistant_content=fallback_msg,
                max_messages=self.chatbot_def.memory.max_messages,
            )
            return
        """

        # 3. 메시지 구성 (히스토리 포함 - Agent 특성)
        messages = self._build_messages_with_history(
            system_prompt=self.chatbot_def.system_prompt,
            history=history,
            user_message=message,
            context=context,
        )

        # 4. LLM 스트리밍 호출 + 메모리 저장
        full_response = []
        for chunk in self._stream_chat(messages):
            full_response.append(chunk)
            yield chunk

        # 5. 메모리 저장 (Agent 특성)
        self.memory.append_pair(
            chatbot_id=self.chatbot_def.id,
            session_id=session_id,
            user_content=message,
            assistant_content="".join(full_response),
            max_messages=self.chatbot_def.memory.max_messages,
        )
