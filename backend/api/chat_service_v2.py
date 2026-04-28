"""
ChatServiceV2 - JSON 기반 계층 구조 + ADK 통합 채팅 서비스

기존 ChatService를 대체하는 새로운 버전입니다.
"""
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional, List, Dict
import json
import time

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.debug_logger import logger
from backend.core.models import ChatSession, Message, ExecutionRole
from backend.conversation.repository import ConversationLog
from backend.api.utils.sse_utils import sse_event, sse_done, sse_error

try:
    from adk_agents.delegation_router_agent import get_router
    ADK_AVAILABLE = True
except ImportError as e:
    logger.error(f"[ChatServiceV2] ADK import failed: {e}")
    ADK_AVAILABLE = False


class ChatServiceV2:
    """
    JSON 기반 계층 구조 챗봇 서비스 (ADK 통합)
    
    특징:
    - ChatbotManager에서 JSON 정의 로드
    - DelegationRouter로 위임 결정
    - SubAgentFactory로 ADK Agent 생성
    - SSE 스트리밍 지원
    """
    
    def __init__(self, chatbot_manager=None, memory_manager=None, conversation_repo=None):
        """
        Args:
            chatbot_manager: 챗봇 관리자 (JSON 로드)
            memory_manager: 메모리 관리자 (대화 히스토리)
            conversation_repo: 대화 저장소
        """
        self.chatbot_manager = chatbot_manager
        self.memory_manager = memory_manager
        self.conversation_repo = conversation_repo
        
        if not ADK_AVAILABLE:
            raise RuntimeError("ADK not available for ChatServiceV2")
        
        self.router = get_router()
        
        # ChatbotManager를 SubAgentFactory에 연결
        if chatbot_manager:
            try:
                from adk_agents.sub_agent_factory import SubAgentFactory
                factory = SubAgentFactory()
                factory.set_chatbot_manager(chatbot_manager)
                logger.info("[ChatServiceV2] Connected ChatbotManager to SubAgentFactory")
            except Exception as e:
                logger.warning(f"[ChatServiceV2] Failed to connect ChatbotManager: {e}")
        
        logger.info("[ChatServiceV2] Initialized")
    
    async def chat_stream(
        self,
        chatbot_id: str,
        message: str,
        session_id: str,
        user_id: str = "user",
        mode: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        챗봇 대화 (스트리밍)
        
        Args:
            chatbot_id: 챗봇 ID
            message: 사용자 메시지
            session_id: 세션 ID
            user_id: 사용자 ID
            mode: 실행 모드 (tool/agent)
            
        Yields:
            SSE 형식 문자열
        """
        start_time = time.time()
        logger.info(f"[ChatServiceV2] chat_stream started for {chatbot_id}, message: {message[:50]}...")
        
        try:
            # 1. 챗봇 정의 로드
            chatbot = self._get_chatbot(chatbot_id)
            if not chatbot:
                logger.error(f"[ChatServiceV2] Chatbot not found: {chatbot_id}")
                yield sse_error(f"Chatbot not found: {chatbot_id}")
                return
            logger.info(f"[ChatServiceV2] Loaded chatbot: {chatbot_id}")
            
            # 2. 권한 확인된 DB ID 목록
            db_ids = self._get_authorized_db_ids(chatbot, user_id)
            logger.info(f"[ChatServiceV2] db_ids for {chatbot_id}: {db_ids}")
            
            # 3. 대화 히스토리 로드
            history = []
            if self.memory_manager:
                history = self.memory_manager.get_history(chatbot_id, session_id)
            
            # 4. 세션 ID를 첫 이벤트로 전송 (UI에서 저장용)
            yield sse_event({"session_id": session_id})
            logger.info(f"[ChatServiceV2] Sent session_id: {session_id}")
            
            # 5. Router 통해 스트리밍 (Agent Tool 방식)
            full_response = []
            logger.info(f"[ChatServiceV2] Starting router stream with tools for {chatbot_id}")
            async for chunk in self.router.route_and_stream_with_tools(
                chatbot_id=chatbot_id,
                message=message,
                session_id=session_id,
                user_id=user_id,
                db_ids=db_ids,
                history=history
            ):
                logger.debug(f"[ChatServiceV2] Yielding chunk: {chunk[:100]}...")
                yield chunk
                
                # SSE 파싱하여 응답 누적
                try:
                    data = json.loads(chunk.replace("data: ", "").strip())
                    if "chunk" in data:
                        full_response.append(data["chunk"])
                except:
                    pass
            
            logger.info(f"[ChatServiceV2] Router stream completed, response length: {len(full_response)}")
            
            # 5. 히스토리 저장
            assistant_response = "".join(full_response)
            self._save_conversation(
                chatbot_id=chatbot_id,
                session_id=session_id,
                user_id=user_id,
                user_message=message,
                assistant_response=assistant_response,
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.error(f"[ChatServiceV2] Chat error: {e}", exc_info=True)
            yield sse_error(str(e))
    
    def _get_chatbot(self, chatbot_id: str):
        """챗봇 정의 조회 (ChatbotDef 또는 Dict 반환)"""
        if self.chatbot_manager:
            return self.chatbot_manager.get_active(chatbot_id)
        
        # Fallback: 직접 JSON 로드
        return self.router._load_chatbot_def(chatbot_id)
    
    def _get_authorized_db_ids(self, chatbot, user_id: str) -> List[str]:
        """권한된 DB ID 목록"""
        # TODO: 실제 권한 체크 로직
        # 현재는 챗봇의 모든 DB 반환
        if hasattr(chatbot, 'retrieval'):
            # ChatbotDef 객체
            return chatbot.retrieval.db_ids if chatbot.retrieval else []
        else:
            # Dict 객체 (fallback)
            capabilities = chatbot.get("capabilities", {})
            return capabilities.get("db_ids", [])
    
    def _save_conversation(
        self,
        chatbot_id: str,
        session_id: str,
        user_id: str,
        user_message: str,
        assistant_response: str,
        duration_ms: int
    ):
        """대화 저장"""
        try:
            # MemoryManager 업데이트
            if self.memory_manager:
                self.memory_manager.append_pair(
                    chatbot_id=chatbot_id,
                    session_id=session_id,
                    user_content=user_message,
                    assistant_content=assistant_response
                )
            
            # ConversationRepository 저장
            if self.conversation_repo:
                from datetime import datetime
                log = ConversationLog(
                    id=0,  # DB에서 auto-increment
                    session_id=session_id,
                    knox_id=user_id,
                    chatbot_id=chatbot_id,
                    user_message=user_message,
                    assistant_response=assistant_response,
                    tokens_used=len(user_message) + len(assistant_response),
                    latency_ms=duration_ms,
                    search_results_count=0,
                    confidence_score=0.0,
                    delegated_to=None,
                    created_at=datetime.now()
                )
                self.conversation_repo.save(log)
            
            logger.info(f"[ChatServiceV2] Conversation saved: {session_id}")
            
        except Exception as e:
            logger.error(f"[ChatServiceV2] Failed to save conversation: {e}")


# 전역 서비스 인스턴스
_service: Optional[ChatServiceV2] = None


def get_chat_service_v2(
    chatbot_manager=None,
    memory_manager=None,
    conversation_repo=None
) -> ChatServiceV2:
    """ChatServiceV2 싱글톤 반환"""
    global _service
    if _service is None:
        _service = ChatServiceV2(
            chatbot_manager=chatbot_manager,
            memory_manager=memory_manager,
            conversation_repo=conversation_repo
        )
    return _service
