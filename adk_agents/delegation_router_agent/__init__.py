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
        logger.info(f"[DelegationRouter] route_and_stream started for {chatbot_id}")
        try:
            # 1. 챗봇 정의 로드
            chatbot_def = self._load_chatbot_def(chatbot_id)
            if not chatbot_def:
                logger.error(f"[DelegationRouter] Chatbot not found: {chatbot_id}")
                yield self._sse_error(f"Chatbot not found: {chatbot_id}")
                return
            logger.info(f"[DelegationRouter] Loaded chatbot definition for {chatbot_id}")

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
            logger.info(f"[DelegationRouter] Selecting target agent for {chatbot_id}")
            target_agent = self._select_target_agent(
                chatbot_def,
                delegation_ctx,
                rag_results
            )
            logger.info(f"[DelegationRouter] Selected agent: {target_agent.name if target_agent else 'None'}")

            # 6. Runner 실행 및 스트리밍
            logger.info(f"[DelegationRouter] Starting _execute_agent_stream")
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
        """RAG 검색 - 실제 ingestion 서버 연결"""
        if not self.ingestion_client:
            logger.warning("[DelegationRouter] IngestionClient not available")
            return []
        
        # 동기 search를 비동기로 실행 (Python 3.9 호환)
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # ThreadPoolExecutor로 동기 함수를 비동기로 실행
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=4)
        
        try:
            results = await loop.run_in_executor(
                executor,
                lambda: self.ingestion_client.search(
                    db_ids=db_ids,
                    query=query,
                    k=5
                )
            )
            logger.info(f"[DelegationRouter] RAG search returned {len(results)} results for db_ids={db_ids}")
            return results
        except Exception as e:
            logger.error(f"[DelegationRouter] RAG search error: {e}")
            return []
    
    def _mock_search_rag(self, query: str, db_ids: List[str]) -> List[Dict]:
        """Mock RAG 검색 결과"""
        mock_results = []
        
        # Query에 따른 Mock 결과 생성
        query_lower = query.lower()
        
        if "인사" in query_lower or "hr" in query_lower or "휴가" in query_lower:
            mock_results.append({
                "content": "인사팀 규정: 연차 휴가는 입사 후 1년 만근 시 15일 발생합니다.",
                "score": 0.95,
                "source": "db_hr_policy"
            })
            mock_results.append({
                "content": "복리후생: 점심 식대는 월 20만원 한도로 지원됩니다.",
                "score": 0.88,
                "source": "db_hr_benefits"
            })
        elif "기술" in query_lower or "개발" in query_lower or "tech" in query_lower or "백엔드" in query_lower:
            mock_results.append({
                "content": "기술스택: 백엔드는 FastAPI, PostgreSQL, Redis를 사용합니다.",
                "score": 0.92,
                "source": "db_tech_stack"
            })
            mock_results.append({
                "content": "개발환경: Docker, Kubernetes 기반의 마이크로서비스 아키텍처",
                "score": 0.85,
                "source": "db_tech_infra"
            })
        else:
            mock_results.append({
                "content": "회사소개: 당사는 2015년 설립된 AI 솔루션 기업입니다.",
                "score": 0.90,
                "source": "db_company_overview"
            })
        
        logger.info(f"[DelegationRouter] Mock RAG returned {len(mock_results)} results")
        return mock_results

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
        """Agent 실행 및 스트리밍 (ADK 세션 관리 사용)"""

        # 기존 세션이 있으면 가져오고, 없으면 생성
        session = await self.session_service.get_session(
            app_name="delegation-router",
            user_id=user_id,
            session_id=session_id
        )
        if not session:
            session = await self.session_service.create_session(
                app_name="delegation-router",
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"[DelegationRouter] Created new ADK session: {session_id}")
        else:
            logger.info(f"[DelegationRouter] Reusing existing ADK session: {session_id} (events: {len(session.events)})")

        runner = Runner(
            agent=agent,
            app_name="delegation-router",
            session_service=self.session_service
        )

        context_prompt = self._build_context_prompt(message, rag_context, confidence)
        content = types.Content(role='user', parts=[types.Part(text=context_prompt)])

        full_response = []
        logger.info(f"[DelegationRouter] Starting runner for session {session_id}")
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content
            ):
                logger.debug(f"[DelegationRouter] Event received: {event}")
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            chunk = part.text
                            full_response.append(chunk)
                            logger.debug(f"[DelegationRouter] Yielding chunk: {chunk[:50]}...")
                            yield self._sse_data(chunk)

            logger.info(f"[DelegationRouter] Runner completed, response length: {len(full_response)}")
            yield self._sse_done("".join(full_response))
        except Exception as e:
            logger.error(f"[DelegationRouter] Runner error: {e}", exc_info=True)
            yield self._sse_error(f"Runner error: {e}")

    async def route_and_stream_with_tools(
        self,
        chatbot_id: str,
        message: str,
        session_id: str,
        user_id: str = "user",
        db_ids: Optional[List[str]] = None,
        history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Agent Tool 방식으로 라우팅 및 스트리밍
        
        하위 Agent를 Tool로 등록하여 LLM이 자동으로 위임 결정
        """
        logger.info(f"[DelegationRouter] route_and_stream_with_tools started for {chatbot_id}")
        
        try:
            # 1. Root Agent + 하위 Agent Tools 생성
            root_agent = self.factory.create_root_agent_with_tools(chatbot_id)
            if not root_agent:
                logger.error(f"[DelegationRouter] Failed to create root agent: {chatbot_id}")
                yield self._sse_error(f"Failed to create agent: {chatbot_id}")
                return
            
            logger.info(f"[DelegationRouter] Created root agent with tools: {root_agent.name}")
            
            # 2. RAG 검색 (컨텍스트용)
            rag_results = []
            if db_ids:
                try:
                    rag_results = await self._search_rag(message, db_ids)
                    logger.info(f"[DelegationRouter] RAG results: {len(rag_results)}")
                except Exception as e:
                    logger.warning(f"[DelegationRouter] RAG search failed: {e}")
            
            # 3. Runner 설정 (ADK 세션 관리 사용)
            # 기존 세션이 있으면 가져오고, 없으면 생성
            session = await self.session_service.get_session(
                app_name="delegation-router",
                user_id=user_id,
                session_id=session_id
            )
            if not session:
                session = await self.session_service.create_session(
                    app_name="delegation-router",
                    user_id=user_id,
                    session_id=session_id
                )
                logger.info(f"[DelegationRouter] Created new ADK session: {session_id}")
            else:
                logger.info(f"[DelegationRouter] Reusing existing ADK session: {session_id} (events: {len(session.events)})")
            
            runner = Runner(
                agent=root_agent,
                app_name="delegation-router",
                session_service=self.session_service
            )
            
            # 4. 프롬프트 구성 (RAG 컨텍스트만 포함, 히스토리는 ADK가 관리)
            if rag_results:
                context = "\n\n[관련 문서]\n" + "\n".join([
                    f"- {r.get('content', '')[:200]}..." for r in rag_results[:3]
                ])
                message_with_context = f"{message}\n\n{context}"
            else:
                message_with_context = message
            
            content = types.Content(role='user', parts=[types.Part(text=message_with_context)])
            
            # 5. Runner 실행 및 스트리밍
            logger.info(f"[DelegationRouter] Starting runner with tools for session {session_id}")
            full_response = []
            
            try:
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content
                ):
                    logger.debug(f"[DelegationRouter] Event received: {type(event).__name__}")
                    
                    # 모든 이벤트에서 content 체크
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                chunk = part.text
                                full_response.append(chunk)
                                logger.debug(f"[DelegationRouter] Yielding chunk: {chunk[:50]}...")
                                yield self._sse_data(chunk)
                            elif hasattr(part, 'function_call') and part.function_call:
                                logger.info(f"[DelegationRouter] Tool call detected: {part.function_call.name}")
                                tool_info = f"[도구 호출: {part.function_call.name}]"
                                yield self._sse_data(tool_info)
                
                logger.info(f"[DelegationRouter] Runner completed, length: {len(full_response)}")
                yield self._sse_done("".join(full_response))
                
            except Exception as e:
                logger.error(f"[DelegationRouter] Runner error: {e}", exc_info=True)
                yield self._sse_error(f"Runner error: {e}")
                
        except Exception as e:
            logger.error(f"[DelegationRouter] Route error: {e}", exc_info=True)
            yield self._sse_error(str(e))

    def _build_context_prompt(
        self,
        message: str,
        rag_results: List[Dict],
        confidence: float
    ) -> str:
        """컨텍스트가 포함된 프롬프트 구성 (출처 포함)"""
        if not rag_results:
            return message

        context_parts = ["[참고 문서]"]
        sources = []
        for i, result in enumerate(rag_results[:3], 1):
            content = result.get("content", "")[:200]
            score = result.get("score", 0)
            source = result.get("source", result.get("db_id", "알 수 없음"))
            context_parts.append(f"{i}. [출처: {source}] (유사도: {score:.2f}) {content}...")
            sources.append(source)

        context_parts.append(f"\n[신뢰도: {confidence:.1f}%]")
        context_parts.append(f"\n[사용자 질문]\n{message}")
        context_parts.append(f"\n[지시사항]\n위 참고 문서를 바탕으로 답변해주세요. 답변 마지막에 사용된 출처를 명시해주세요.")
        if sources:
            context_parts.append(f"\n[사용된 출처] {', '.join(set(sources))}")

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
