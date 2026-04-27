"""
backend/api/chat_service_adk.py - ADK 기반 채팅 서비스
Google ADK를 사용하여 챗봇 응답 생성
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

# ADK Agents 디렉토리를 Python 경로에 추가
ADK_AGENTS_DIR = Path(__file__).parent.parent.parent / "adk_agents"
sys.path.insert(0, str(ADK_AGENTS_DIR))

from backend.config import settings
from backend.debug_logger import logger
from backend.api.utils.sse_utils import sse_event, sse_done, sse_error
from backend.core.models import ExecutionRole

# ADK import
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.sessions import Session
    from google.adk.memory import InMemoryMemoryService
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    from google.genai import types
    ADK_AVAILABLE = True
except ImportError as e:
    logger.error(f"ADK import failed: {e}")
    ADK_AVAILABLE = False

# 환경에 따른 모델 설정
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

def create_adk_model():
    """환경에 따른 ADK 모델 생성"""
    if IS_DEVELOPMENT:
        # 개발환경: Ollama
        return LiteLlm(
            model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5')}",
            api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
        )
    else:
        # 사내환경
        return LiteLlm(
            model=f"openai/{os.getenv('LLM_DEFAULT_MODEL', 'GLM4.7')}",
            api_base=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:11434/v1"),
            api_key=os.getenv("LLM_API_KEY", "")
        )


class ADKChatService:
    """ADK 기반 채팅 서비스"""

    def __init__(self):
        self.session_service = InMemorySessionService()
        self.memory_service = InMemoryMemoryService()
        self._agents: dict[str, Agent] = {}
        logger.info(f"[ADKChatService] Initialized with DEVELOPMENT={IS_DEVELOPMENT}")

    def _get_or_create_agent(self, chatbot_id: str, system_prompt: str = "") -> Optional[Agent]:
        """챗봿 ID에 해당하는 ADK 에이전트 생성 또는 캐시에서 반환"""
        if chatbot_id in self._agents:
            return self._agents[chatbot_id]

        if not ADK_AVAILABLE:
            logger.error("ADK not available")
            return None

        try:
            # adk_agents에서 해당 챗봇 모듈 로드 시도
            module_name = f"{chatbot_id}_adk" if not chatbot_id.endswith("_adk") else chatbot_id
            try:
                module = __import__(module_name, fromlist=['root_agent'])
                agent = module.root_agent
                logger.info(f"[ADKChatService] Loaded agent from {module_name}")
            except ImportError:
                # 모듈이 없으면 기본 에이전트 생성
                logger.warning(f"[ADKChatService] Module {module_name} not found, creating default agent")
                model = create_adk_model()
                agent = Agent(
                    name=chatbot_id,
                    model=model,
                    instruction=system_prompt or "당신은 유용한 어시스턴트입니다. 한국어로 답변하세요.",
                    description=f"ADK agent for {chatbot_id}"
                )

            self._agents[chatbot_id] = agent
            return agent

        except Exception as e:
            logger.error(f"[ADKChatService] Failed to create agent: {e}")
            return None

    async def stream_chat_response(
        self,
        chatbot_id: str,
        message: str,
        session_id: str,
        user: dict,
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        ADK를 사용하여 채팅 응답 스트리밍
        """
        if not ADK_AVAILABLE:
            yield sse_error("ADK not available. Please install google-adk.")
            return

        # 세션 ID 전송
        yield sse_event(json.dumps({"session_id": session_id}), event="session")

        # 에이전트 가져오기
        agent = self._get_or_create_agent(chatbot_id, system_prompt)
        if not agent:
            yield sse_error(f"Failed to create agent for {chatbot_id}")
            return

        # ADK 세션 생성/가져오기
        user_id = user.get("knox_id", "anonymous")
        adk_session = self.session_service.create_session(
            app_name="multi-agent-service",
            user_id=user_id,
            session_id=session_id,
            state={}
        )

        # 메모리에 사용자 메시지 저장
        self.memory_service.add_message_to_memory(
            app_name="multi-agent-service",
            user_id=user_id,
            session_id=session_id,
            message={"role": "user", "content": message}
        )

        # ADK 실행
        full_response = []
        try:
            # Runner.run을 사용하여 에이전트 실행
            from google.adk.runners import Runner

            runner = Runner(
                agent=agent,
                app_name="multi-agent-service",
                session_service=self.session_service,
                memory_service=self.memory_service
            )

            # 메시지 구성
            content = types.Content(role='user', parts=[types.Part(text=message)])

            # 스트리밍 실행
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            full_response.append(part.text)
                            yield sse_event(part.text)

            # 메모리에 어시스턴트 응답 저장
            response_text = "".join(full_response)
            self.memory_service.add_message_to_memory(
                app_name="multi-agent-service",
                user_id=user_id,
                session_id=session_id,
                message={"role": "assistant", "content": response_text}
            )

            # 저장
            await self._save_conversation(
                session_id=session_id,
                user=user,
                message=message,
                response=response_text,
                chatbot_id=chatbot_id
            )

        except Exception as e:
            logger.error(f"[ADKChatService] Error during execution: {e}", exc_info=True)
            yield sse_error(f"Execution error: {str(e)}")

        yield sse_done()

    async def _save_conversation(
        self,
        session_id: str,
        user: dict,
        message: str,
        response: str,
        chatbot_id: str
    ):
        """대화 저장"""
        try:
            # TODO: PostgreSQL/Mock 저장소 연동
            logger.info(f"[ADKChatService] Conversation saved: {session_id}")
        except Exception as e:
            logger.error(f"[ADKChatService] Failed to save conversation: {e}")


# 전역 서비스 인스턴스
_adk_chat_service: Optional[ADKChatService] = None

def get_adk_chat_service() -> ADKChatService:
    """ADK ChatService 싱글톤 반환"""
    global _adk_chat_service
    if _adk_chat_service is None:
        _adk_chat_service = ADKChatService()
    return _adk_chat_service
