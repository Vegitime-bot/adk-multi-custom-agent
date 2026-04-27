"""
DelegationRouterAgent - JSON 기반 계층 구조의 중앙 라우터
"""
import os
import sys
import json
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any, List

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.debug_logger import logger
from backend.config import settings

# ADK import
try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from google.adk.models.lite_llm import LiteLlm
    ADK_AVAILABLE = True
except ImportError as e:
    logger.error(f"[DelegationRouterAgent] ADK import failed: {e}")
    ADK_AVAILABLE = False

from adk_agents.sub_agent_factory import SubAgentFactory
from adk_agents.tools.delegation_tools import (
    calculate_confidence,
    select_sub_chatbot,
    extract_keywords,
    DelegationContext
)

# 모델 설정
IS_DEVELOPMENT = os.getenv("DEVELOPMENT", "false").lower() == "true"

if IS_DEVELOPMENT:
    model = LiteLlm(
        model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
        api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
    )
else:
    # 사내 서버: config.py 설정 사용
    model = LiteLlm(
        model=f"openai/{settings.LLM_DEFAULT_MODEL}",
        api_base=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY
    )


class DelegationRouter:
    """
    JSON 챗봇 계층 구조의 중앙 라우터
    """

    def __init__(self):
        if not ADK_AVAILABLE:
            raise RuntimeError("ADK not available")

        self.factory = SubAgentFactory(model=model)
        self.session_service = InMemorySessionService()

        # IngestionClient (RAG 검색)
        try:
            from backend.retrieval.ingestion_client import get_ingestion_client
            self.ingestion_client = get_ingestion_client()
        except Exception as e:
            logger.warning(f"[DelegationRouter] IngestionClient not available: {e}")
            self.ingestion_client = None

        logger.info("[DelegationRouter] Initialized")

    async def route_and_stream(
        self,
        chatbot_id: str,
        message: str,
        session_id: str,
        user_id: str = "user",
        db_ids: Optional[List[str]] = None,
        history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        """라우팅 및 SSE 스트리밍"""
        try:
            # 1. 챗봇 정의 로드
            chatbot_def = self._load_chatbot_def(chatbot_id)
            if not chatbot_def:
                yield self._sse_error(f"Chatbot not found: {chatbot_id}")
                return

            # 2. RAG 검색
            rag_results = []
            if self.ingestion_client and db_ids:
                try:
                    rag_results = await self._search_rag(message, db_ids)
                except Exception as e:
                    logger.warning(f"[DelegationRouter] RAG search failed: {e}")

            # 3. 신뢰도 계산
            confidence = calculate_confidence(rag_results)
            sub_chatbots = chatbot_def.get("sub_chatbots", [])

            # 4. 위임 결정
            delegation_ctx = DelegationContext(
                chatbot_id=chatbot_id,
                query=message,
                rag_results=rag_results,
                confidence=confidence,
                sub_chatbots=sub_chatbots,
                parent_id=chatbot_def.get("parent_id")
            )

            # 5. 적절한 Agent 선택
            target_agent = self._select_target_agent(
                chatbot_def,
                delegation_ctx,
                rag_results
            )

            # 6. Runner 실행 및 스트리밍
            async for chunk in self._execute_agent_stream(
                agent=target_agent,
                message=message,
                session_id=session_id,
                user_id=user_id,
                rag_context=rag_results,
                confidence=confidence
            ):
                yield chunk

        except Exception as e:
            logger.error(f"[DelegationRouter] Route error: {e}", exc_info=True)
            yield self._sse_error(str(e))

    def _load_chatbot_def(self, chatbot_id: str) -> Optional[Dict[str, Any]]:
        """챗봇 정의 로드"""
        return self.factory._get_chatbot_def(chatbot_id)

    async def _search_rag(self, query: str, db_ids: List[str]) -> List[Dict]:
        """RAG 검색"""
        if not self.ingestion_client:
            return []

        results = []
        for db_id in db_ids:
            try:
                search_results = await self.ingestion_client.search_async(
                    db_id=db_id,
                    query=query,
                    top_k=5
                )
                results.extend(search_results)
            except Exception as e:
                logger.warning(f"[DelegationRouter] Search failed for {db_id}: {e}")

        return results

    def _select_target_agent(
        self,
        chatbot_def: Dict[str, Any],
        delegation_ctx: DelegationContext,
        rag_results: List[Dict]
    ) -> Agent:
        """위임 결정 및 대상 Agent 선택"""
        chatbot_id = chatbot_def["id"]

        if not delegation_ctx.should_delegate:
            logger.info(f"[DelegationRouter] Direct response from {chatbot_id}")
            return self.factory.create_agent(chatbot_def)

        if delegation_ctx.selected_sub:
            sub_id = delegation_ctx.selected_sub["id"]
            logger.info(f"[DelegationRouter] Delegating {chatbot_id} -> {sub_id}")

            sub_def = self._load_chatbot_def(sub_id)
            if sub_def:
                return self.factory.create_agent(sub_def)

        logger.warning(f"[DelegationRouter] Delegation failed, fallback to {chatbot_id}")
        return self.factory.create_agent(chatbot_def)

    async def _execute_agent_stream(
        self,
        agent: Agent,
        message: str,
        session_id: str,
        user_id: str,
        rag_context: List[Dict],
        confidence: float
    ) -> AsyncGenerator[str, None]:
        """Agent 실행 및 스트리밍"""

        session = await self.session_service.create_session(
            app_name="delegation-router",
            user_id=user_id,
            session_id=session_id
        )

        runner = Runner(
            agent=agent,
            app_name="delegation-router",
            session_service=self.session_service
        )

        context_prompt = self._build_context_prompt(message, rag_context, confidence)
        content = types.Content(role='user', parts=[types.Part(text=context_prompt)])

        full_response = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        chunk = part.text
                        full_response.append(chunk)
                        yield self._sse_data(chunk)

        yield self._sse_done("".join(full_response))

    def _build_context_prompt(
        self,
        message: str,
        rag_results: List[Dict],
        confidence: float
    ) -> str:
        """컨텍스트가 포함된 프롬프트 구성"""
        if not rag_results:
            return message

        context_parts = ["[참고 문서]"]
        for i, result in enumerate(rag_results[:3], 1):
            content = result.get("content", "")[:200]
            score = result.get("score", 0)
            context_parts.append(f"{i}. (유사도: {score:.2f}) {content}...")

        context_parts.append(f"\n[신뢰도: {confidence:.1f}%]")
        context_parts.append(f"\n[사용자 질문]\n{message}")

        return "\n".join(context_parts)

    def _sse_data(self, data: str) -> str:
        """SSE 데이터 이벤트 포맷"""
        return f"data: {json.dumps({'chunk': data}, ensure_ascii=False)}\n\n"

    def _sse_error(self, error: str) -> str:
        """SSE 에러 이벤트 포맷"""
        return f"data: {json.dumps({'error': error}, ensure_ascii=False)}\n\n"

    def _sse_done(self, full_response: str) -> str:
        """SSE 완료 이벤트 포맷"""
        return f"data: {json.dumps({'done': True, 'response': full_response}, ensure_ascii=False)}\n\n"


# 전역 라우터 인스턴스
_router: Optional[DelegationRouter] = None


def get_router() -> DelegationRouter:
    """라우터 싱글톤 반환"""
    global _router
    if _router is None:
        _router = DelegationRouter()
    return _router


# ADK Agent로서의 인터페이스 (간접 호출용)
agent = Agent(
    name="delegation_router",
    model=model,
    instruction="""
    JSON 기반 챗봇 계층 구조의 중앙 라우터입니다.

    다른 코드에서 DelegationRouter 클래스를 직접 인스턴스화하여 사용하세요.
    이 agent는 식별자/문서화용입니다.
    """
)
