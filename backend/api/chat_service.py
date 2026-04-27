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

# USE_MOCK_DB 설정에 따라 저장소 선택
if settings.USE_MOCK_DB:
    # Mock Repository 사용 (파일 기반)
    from backend.repository.mock_repository import (
        MockSessionRepository,
        MockMessageRepository,
        MockDelegationRepository
    )
    SessionRepository = MockSessionRepository
    MessageRepository = MockMessageRepository
    DelegationRepository = MockDelegationRepository
    USE_DB_SESSION = False
else:
    # PostgreSQL Repository 사용
    from backend.repository import (
        PostgreSQLSessionRepository,
        PostgreSQLMessageRepository,
        PostgreSQLDelegationRepository
    )
    from backend.database.session import get_db_session as get_db
    SessionRepository = PostgreSQLSessionRepository
    MessageRepository = PostgreSQLMessageRepository
    DelegationRepository = PostgreSQLDelegationRepository
    USE_DB_SESSION = True
    logger.info("[ChatService] Using PostgreSQL repositories")


class ChatService:
    """채팅 비즈니스 로직 서비스"""

    def __init__(self):
        self.conv_repo = MockConversationRepository()
        logger.info(f"[ChatService] Initialized with USE_MOCK_DB={settings.USE_MOCK_DB}")

    def _get_repos(self):
        """설정에 따라 저장소 반환 (Context Manager)"""
        if USE_DB_SESSION:
            db = next(get_db())
            try:
                yield SessionRepository(db), MessageRepository(db), DelegationRepository(db)
            finally:
                db.close()
        else:
            yield SessionRepository(), MessageRepository(), DelegationRepository()

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

        # 대화 기록 저장 (Mock 저장소에)
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
        """대화 기록 저장 (Mock 저장소)"""
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

        # 2. PostgreSQL/Mock 저장소에 저장
        try:
            # 저장소 가져오기 (DB 세션 자동 관리)
            repos = self._get_repos()
            session_repo, message_repo, _ = next(repos)
            
            # 먼저 세션이 존재하는지 확인, 없으면 생성
            existing_session = session_repo.get_by_id(session_id)
            if not existing_session:
                logger.info(f"[Chat {request_id}] 새 세션 생성: {session_id}")
                session_repo.create(
                    user_id=knox_id,
                    chatbot_id=chatbot_id,
                    session_id=session_id
                )
            
            # 사용자 메시지 저장
            message_repo.create(
                session_id=session_id,
                role='user',
                content=message,
                tokens_used=len(message.split()),
                latency_ms=0,
                confidence_score=None,
                delegated_to=None
            )

            # 어시스턴트 응답 저장
            message_repo.create(
                session_id=session_id,
                role='assistant',
                content=response_text,
                tokens_used=tokens,
                latency_ms=latency_ms,
                confidence_score=confidence_score,
                delegated_to=delegated_to
            )

            logger.info(f"[Chat {request_id}] 저장소 저장 완료")
        except Exception as e:
            logger.error(f"[Chat {request_id}] 저장소 저장 실패: {e}")

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
