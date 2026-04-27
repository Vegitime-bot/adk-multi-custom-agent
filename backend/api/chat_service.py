"""
backend/api/chat_service.py - 채팅 비즈니스 로직 서비스
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict, Any

from backend.config import settings
from backend.debug_logger import logger
from backend.core.models import ExecutionRole
from backend.conversation.repository import (
    ConversationLog,
    MockConversationRepository,
)
from backend.api.utils.sse_utils import sse_event, sse_done, sse_error
from backend.api.middleware.auth_middleware import (
    get_user_permissions,
    check_chatbot_access,
    check_mode_permission,
)
from backend.api.utils.chat_utils import (
    resolve_execution_mode,
    create_executor,
)

# PostgreSQL Repository import
try:
    from backend.repository import PostgreSQLMessageRepository, PostgreSQLDelegationRepository
    from backend.database.session import get_db_context
    USE_POSTGRES = True
except ImportError:
    USE_POSTGRES = False



class ChatService:
    """채팅 비즈니스 로직 서비스"""

    def __init__(self):
        self.conv_repo = MockConversationRepository()

    async def stream_chat_response(
        self,
        chatbot_id: str,
        message: str,
        session_id: str,
        mode: ExecutionRole,
        user: dict,
        executor,
        chatbot_mgr,
        session_mgr,
        memory_mgr,
        multi_sub_execution: Optional[bool] = None,
    ) -> AsyncGenerator[str, None]:
        """
        채팅 응답을 SSE 스트림으로 생성

        Args:
            chatbot_id: 챗봇 ID
            message: 사용자 메시지
            session_id: 세션 ID
            mode: 실행 모드
            user: 사용자 정보
            executor: 실행기
            chatbot_mgr: 챗봇 관리자
            session_mgr: 세션 관리자
            memory_mgr: 메모리 관리자
            multi_sub_execution: 하위 챗봇 다중 실행 여부

        Yields:
            str: SSE 이벤트 문자열
        """
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}"

        # 먼저 session_id 전송
        yield sse_event(json.dumps({"session_id": session_id}), event="session")

        full_response = []
        chunk_count = 0
        llm_start_time = time.time()
        search_results_count = 0
        confidence_score = None
        delegated_to = None

        # Executor에서 추가 정보 추출
        if hasattr(executor, '_last_search_results'):
            search_results_count = len(executor._last_search_results)
        if hasattr(executor, '_last_confidence'):
            confidence_score = executor._last_confidence
        if hasattr(executor, '_last_delegated_to'):
            delegated_to = executor._last_delegated_to

        try:
            for chunk in executor.execute(message, session_id):
                chunk_count += 1
                full_response.append(chunk)
                yield sse_event(chunk)

                if chunk_count % 100 == 0:
                    elapsed = time.time() - llm_start_time
                    logger.info(f"[Chat {request_id}] 스트리밍 중... {chunk_count} chunks")

        except Exception as e:
            logger.error(f"[Chat {request_id}] 스트리밍 실패: {str(e)}")
            logger.error(f"[Chat {request_id}] {traceback.format_exc()}")
            yield sse_error(f"실행 오류: {str(e)}")
            return

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"[Chat {request_id}] 스트리밍 완료: {chunk_count} chunks, {llm_elapsed:.1f}s")

        yield sse_done()

        # 대화 기록 저장
        await self._save_conversation_log(
            request_id=request_id,
            session_id=session_id,
            user=user,
            chatbot_id=chatbot_id,
            message=message,
            full_response=full_response,
            chunk_count=chunk_count,
            llm_elapsed=llm_elapsed,
            search_results_count=search_results_count,
            confidence_score=confidence_score,
            delegated_to=delegated_to,
        )

        total_elapsed = time.time() - start_time
        logger.info(f"[Chat {request_id}] ========== 완료 ({total_elapsed:.1f}s) ==========")

    async def _save_conversation_log(
        self,
        request_id: str,
        session_id: str,
        user: dict,
        chatbot_id: str,
        message: str,
        full_response: list,
        chunk_count: int,
        llm_elapsed: float,
        search_results_count: int,
        confidence_score: Optional[float],
        delegated_to: Optional[str],
    ):
        """대화 기록 저장 (PostgreSQL + 기존 저장소)"""
        knox_id = user.get("knox_id", "unknown")
        response_text = "".join(full_response)
        tokens = chunk_count * 4  # Approximate
        latency_ms = int(llm_elapsed * 1000)
        
        # 1. 기존 저장소에 저장
        try:
            conv_log = ConversationLog(
                id=None,
                session_id=session_id,
                knox_id=knox_id,
                chatbot_id=chatbot_id,
                user_message=message,
                assistant_response=response_text,
                tokens_used=tokens,
                latency_ms=latency_ms,
                search_results_count=search_results_count,
                confidence_score=confidence_score,
                delegated_to=delegated_to,
                created_at=datetime.now(),
            )
            self.conv_repo.save(conv_log)
        except Exception as e:
            logger.error(f"[Chat {request_id}] 기존 저장소 저장 실패: {e}")
        
        # 2. PostgreSQL에 저장 (사용자 메시지 + 어시스턴트 응답)
        if USE_POSTGRES:
            try:
                with get_db_context() as db:
                    msg_repo = PostgreSQLMessageRepository(db)
                    
                    # 사용자 메시지 저장
                    msg_repo.create(
                        session_id=session_id,
                        role='user',
                        content=message,
                        tokens_used=len(message.split()),  # 단어 수로 근사
                        latency_ms=0,
                        confidence_score=None,
                        delegated_to=None
                    )
                    
                    # 어시스턴트 응답 저장
                    msg_repo.create(
                        session_id=session_id,
                        role='assistant',
                        content=response_text,
                        tokens_used=tokens,
                        latency_ms=latency_ms,
                        confidence_score=confidence_score,
                        delegated_to=delegated_to
                    )
                    
                    logger.info(f"[Chat {request_id}] PostgreSQL 저장 완료")
            except Exception as e:
                logger.error(f"[Chat {request_id}] PostgreSQL 저장 실패: {e}")
        
        logger.info(f"[Chat {request_id}] 대화 기록 저장 완료")

    async def stream_tool_response(
        self,
        chatbot_id: str,
        message: str,
        user: dict,
        executor,
    ) -> AsyncGenerator[str, None]:
        """Tool 모드 전용 응답 스트리밍"""
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}"

        full_response = []
        chunk_count = 0

        try:
            for chunk in executor.execute(message, session_id=None):
                chunk_count += 1
                full_response.append(chunk)
                yield sse_event(chunk)

        except Exception as e:
            logger.error(f"[Tool {request_id}] 오류: {str(e)}")
            yield sse_error(f"실행 오류: {str(e)}")
            return

        yield sse_done()
        logger.info(f"[Tool {request_id}] 완료 ({len(''.join(full_response))}자)")


# 전역 서비스 인스턴스
chat_service = ChatService()


def get_chat_service() -> ChatService:
    """ChatService 인스턴스 반환"""
    return chat_service
