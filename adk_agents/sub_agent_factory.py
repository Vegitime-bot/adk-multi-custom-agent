"""
SubAgentFactory - JSON 정의를 ADK Agent로 변환하는 팩토리
"""
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 중첩 이벤트 루프 허용 (프로세스 레벨에서 한 번만)
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass  # 없으면 skip (서버 실행 시 별도 설치 권장)

from backend.debug_logger import logger

# ADK import
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.tools.agent_tool import AgentTool
    from google.adk.tools.function_tool import FunctionTool
    ADK_AVAILABLE = True
except ImportError as e:
    ADK_AVAILABLE = False
    logger.error(f"[SubAgentFactory] ADK not available: {e}")
    Agent = None
    LiteLlm = None
    AgentTool = None
    FunctionTool = None

from adk_agents.tools.delegation_tools import calculate_confidence, select_sub_chatbot, should_delegate


# ── 모듈 레벨 헬퍼 ────────────────────────────────────────────────
def _extract_db_ids(chatbot_def: Dict[str, Any]) -> List[str]:
    """챗봇 정의에서 db_ids 추출 (capabilities/retrieval 두 구조 모두 지원)"""
    caps = chatbot_def.get("capabilities", {})
    if caps and isinstance(caps, dict):
        db_ids = caps.get("db_ids", [])
        if db_ids:
            return db_ids

    retrieval = chatbot_def.get("retrieval")
    if retrieval:
        if hasattr(retrieval, 'db_ids'):
            return list(retrieval.db_ids)
        elif isinstance(retrieval, dict):
            db_ids = retrieval.get("db_ids", [])
            if db_ids:
                return db_ids

    if hasattr(chatbot_def, 'capabilities'):
        caps = chatbot_def.capabilities
        if hasattr(caps, 'db_ids'):
            return list(caps.db_ids)

    return []


class SubAgentFactory:
    """JSON 챗봇 정의를 ADK Agent로 변환하는 팩토리"""
    
    def __init__(self, model=None):
        if not ADK_AVAILABLE:
            raise RuntimeError("ADK not available")
        
        self.model = model or self._get_default_model()
        self._agent_cache: Dict[str, Agent] = {}
        self._chatbot_defs: Dict[str, Dict] = {}  # 동적 정의 캐시
        self._chatbot_manager = None  # ChatbotManager 참조
        logger.info("[SubAgentFactory] Initialized")
    
    def set_chatbot_manager(self, chatbot_manager):
        """ChatbotManager 주입"""
        self._chatbot_manager = chatbot_manager
        logger.info("[SubAgentFactory] ChatbotManager set")
    
    def set_chatbot_def(self, chatbot_id: str, chatbot_def: Dict):
        """동적 챗봇 정의 주입"""
        self._chatbot_defs[chatbot_id] = chatbot_def
        logger.info(f"[SubAgentFactory] Chatbot definition injected: {chatbot_id}")
    
    def _get_default_model(self) -> LiteLlm:
        """기본 모델 설정 - config.py 사용"""
        from backend.config import settings
        
        is_dev = os.getenv("DEVELOPMENT", "false").lower() == "true"
        
        if is_dev:
            # 개발환경: Ollama (config.py 또는 환경변수)
            return LiteLlm(
                model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
                api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
            )
        else:
            # 사내 서버: config.py의 LLM 설정 사용
            return LiteLlm(
                model=f"openai/{settings.LLM_DEFAULT_MODEL}",
                api_base=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY
            )
    
    def create_agent(self, chatbot_def: Dict[str, Any]) -> Agent:
        chatbot_id = chatbot_def["id"]
        agent_name = chatbot_id.replace("-", "_")

        if chatbot_id in self._agent_cache:
            return self._agent_cache[chatbot_id]

        db_ids = _extract_db_ids(chatbot_def)
        has_rag_tool = len(db_ids) > 0
        logger.info(f"[SubAgentFactory] Creating agent for {chatbot_id} | db_ids={db_ids} | has_rag_tool={has_rag_tool}")

        system_prompt = self._build_system_prompt(chatbot_def, has_rag_tool)

        tools = []
        if has_rag_tool:
            rag_tool = self._build_rag_tool(chatbot_id, db_ids)
            if rag_tool:
                tools.append(rag_tool)
                logger.info(f"[SubAgentFactory] Added RAG search tool for {chatbot_id} with db_ids={db_ids}")

        # 하위 챗봘을 AgentTool로 등록 (N단계 위임 지원)
        sub_chatbots = chatbot_def.get("sub_chatbots", [])
        for sub in sub_chatbots:
            sub_id = self._get_sub_id(sub)
            if sub_id:
                sub_tool = self.create_agent_tool(sub_id)
                if sub_tool:
                    tools.append(sub_tool)
                    logger.info(f"[SubAgentFactory] Added sub tool {sub_id} to {chatbot_id}")

        agent_kwargs = dict(
            name=agent_name,
            model=self.model,
            instruction=system_prompt,
            description=chatbot_def.get("description", ""),
        )
        if tools:
            agent_kwargs["tools"] = tools

        agent = Agent(**agent_kwargs)
        self._agent_cache[chatbot_id] = agent
        logger.info(f"[SubAgentFactory] Created agent {chatbot_id} with {len(tools)} tools (rag={has_rag_tool})")
        return agent

    def _build_rag_tool(self, chatbot_id: str, db_ids: List[str]) -> Optional[Any]:
        if not ADK_AVAILABLE or FunctionTool is None:
            logger.error(f"[SubAgentFactory] FunctionTool not available for RAG tool")
            return None

        try:
            from backend.retrieval.ingestion_client import get_ingestion_client
            ingestion_client = get_ingestion_client()
        except Exception as e:
            logger.error(f"[SubAgentFactory] IngestionClient not available: {e}")
            return None

        def rag_search(query: str) -> str:
            logger.info(f"[RAG-Tool] chatbot_id={chatbot_id} | query={query[:200]} | db_ids={db_ids}")
            try:
                results = ingestion_client.search(db_ids=db_ids, query=query, k=5)
                result_count = len(results)
                logger.info(f"[RAG-Tool] chatbot_id={chatbot_id} | result_count={result_count}")
                if not results:
                    return "[RAG 검색 결과] 해당 쿼리에 일치하는 문서가 없습니다."
                formatted = ingestion_client.format_results(results, max_length=500, show_score=True)
                return f"[RAG 검색 결과] (검색된 문서 수: {result_count})\n\n{formatted}"
            except Exception as e:
                logger.error(f"[RAG-Tool] chatbot_id={chatbot_id} | search error: {e}", exc_info=True)
                return f"[RAG 검색 오류] {str(e)}"

        safe_name = f"rag_search_{chatbot_id.replace('-', '_')}"
        rag_search.name = safe_name
        rag_search.doc = (
            f"Retrieve relevant documents from databases {db_ids} based on the given query. "
            f"Use this tool to search for information before answering questions."
        )

        tool = FunctionTool(func=rag_search)
        logger.info(f"[SubAgentFactory] Created RAG FunctionTool '{safe_name}' for {chatbot_id} with db_ids={db_ids}")
        return tool
    
    def _build_system_prompt(self, chatbot_def: Dict[str, Any], has_rag_tool: bool = False) -> str:
        """시스템 프롬프트 구성"""
        capabilities = chatbot_def.get("capabilities", {})
        policy = chatbot_def.get("policy", {})
        
        base_prompt = capabilities.get("system_prompt", "")
        
        # 위임 관련 프롬프트 추가
        has_subs = bool(chatbot_def.get("sub_chatbots"))
        threshold = policy.get("delegation_threshold", 70)
        
        if has_subs:
            delegation_prompt = f"""

[위임 지침]
당신은 상위 챗봇으로서 다음 하위 전문가들을 관리합니다:
{self._format_sub_chatbots(chatbot_def.get("sub_chatbots", []))}

응답 전략:
1. 질문에 대해 먼저 스스로 답변을 시도하세요
2. 답변 끝에 "CONFIDENCE: XX" 형식으로 신뢰도를 표시하세요 (0-100)
3. 신뢰도가 {threshold}% 미만이거나 전문 상담이 필요하면 하위 전문가에게 위임하세요
4. 하위 전문가에게 위임할 때는 반드시 해당 전문가의 도구를 호출하세요
5. 텍스트로 "DELEGATE_TO:"를 쓰지 마세요. 반드시 도구 호출(function calling)을 사용하세요

[출처 표시 규칙 - 반드시 준수]
답변 마지막에 반드시 다음 형식으로 출처를 표시하세요:

---
📚 **출처**: 
- [RAG] 검색된 문서 기반 답변 (검색 결과 사용 시)
- [LLM] AI 생성 답변 (일반 지식/추론 기반 시)
- [RAG+LLM] 문서 기반 + AI 보충 설명 (혼합 시)

예시:
---
📚 **출처**: [RAG] 기술스택 문서 (db_tech_stack), 개발환경 가이드 (db_dev_guide)
---
📚 **출처**: [LLM] 일반 기술 지식 기반 생성
---
📚 **출처**: [RAG+LLM] 기술스택 문서 + AI 보충 설명

상위 Agent로부터 위임받은 경우, 축적된 컨텍스트를 활용하세요.
"""
            if has_rag_tool:
                delegation_prompt += """

[RAG 검색 도구 사용 규칙 - 반드시 준수]
1. 직접 답변하기 전, rag_search 도구를 사용하여 관련 문서를 검색하세요
2. 검색 결과 없이 추측하여 답변하지 마세요
3. 검색 결과가 없으면 하위 전문가에게 위임하거나 '검색 결과가 없습니다'라고 답변하세요
"""
            # 사용자 프롬프트를 가장 마지막에 배치 (우선순위 최고)
            base_prompt = delegation_prompt + "\n\n" + base_prompt
        else:
            # Leaf 챗봇
            leaf_prompt = """

[리프 챗봇 지침]
당신은 전문 영역의 최하위 챗봇입니다.
- 검색된 문서를 기반으로 정확하게 답변하세요
- 전문 분야 외 질문에는 "해당 내용은 제 전문 분야가 아닙니다"라고 답변하세요
- 상위 Agent로부터 위임받은 경우, 컨텍스트를 참고하세요

[출처 표시 규칙 - 반드시 준수]
답변 마지막에 반드시 다음 형식으로 출처를 표시하세요:

---
📚 **출처**: 
- [RAG] 검색된 문서 기반 답변 (검색 결과 사용 시)
- [LLM] AI 생성 답변 (일반 지식/추론 기반 시)
- [RAG+LLM] 문서 기반 + AI 보충 설명 (혼합 시)

예시:
---
📚 **출처**: [RAG] 기술스택 문서 (db_tech_stack), 개발환경 가이드 (db_dev_guide)
---
📚 **출처**: [LLM] 일반 기술 지식 기반 생성
---
📚 **출처**: [RAG+LLM] 기술스택 문서 + AI 보충 설명
"""
            if has_rag_tool:
                leaf_prompt += """

[RAG 검색 도구 사용 규칙 - 반드시 준수]
1. 질문에 답하기 전, 반드시 rag_search 도구를 사용하여 관련 문서를 검색하세요
2. 검색 결과 없이 추측하여 답변하지 마세요
3. 검색 결과가 없으면 '해당 질문에 대한 문서가 없습니다'라고 답변하세요
4. 답변은 검색된 문서 내용에만 기반하여 작성하세요
"""
            # 사용자 프롬프트를 가장 마지막에 배치 (우선순위 최고)
            base_prompt = leaf_prompt + "\n\n" + base_prompt
        
        return base_prompt
    
    def _get_sub_id(self, sub) -> str:
        """SubChatbotRef 객체 또는 dict에서 id 추출"""
        if hasattr(sub, 'id'):
            return sub.id
        elif isinstance(sub, dict):
            return sub.get("id", "unknown")
        return "unknown"
    
    def _format_sub_chatbots(self, sub_chatbots: List[Dict]) -> str:
        """하위 챗봘 목록 포맷팅"""
        lines = []
        for sub in sub_chatbots:
            sub_id = self._get_sub_id(sub)
            sub_def = self._get_chatbot_def(sub_id)
            if sub_def:
                desc = sub_def.get("description", "")
                keywords = sub_def.get("policy", {}).get("keywords", [])[:5]
                lines.append(f"- {sub_id}: {desc} (키워드: {', '.join(keywords)})")
        return "\n".join(lines) if lines else "(하위 챗봇 정보 없음)"
    
    def _get_chatbot_def(self, chatbot_id: str) -> Optional[Dict[str, Any]]:
        """챗봇 정의 조회 (동적 정의 → ChatbotManager → JSON 파일 순)"""
        # 1. 동적 정의 캐시 먼저 확인
        if chatbot_id in self._chatbot_defs:
            return self._chatbot_defs[chatbot_id]
        
        # 2. ChatbotManager에서 조회
        if self._chatbot_manager:
            chatbot = self._chatbot_manager.get_active(chatbot_id)
            if chatbot:
                # ChatbotDef 객체를 Dict로 변환
                return self._chatbot_def_to_dict(chatbot)
        
        # 3. JSON 파일에서 로드 (Fallback)
        chatbots_dir = PROJECT_ROOT / "chatbots"
        json_file = chatbots_dir / f"{chatbot_id}.json"
        
        if json_file.exists():
            import json
            with open(json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        logger.warning(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
        return None
    
    def _chatbot_def_to_dict(self, chatbot_def) -> Dict:
        """ChatbotDef 객체를 Dict로 변환 (Pydantic model 지원)"""
        if isinstance(chatbot_def, dict):
            return chatbot_def
        
        # Pydantic model인 경우
        if hasattr(chatbot_def, 'model_dump'):
            # Pydantic v2
            return chatbot_def.model_dump()
        elif hasattr(chatbot_def, 'dict'):
            # Pydantic v1
            return chatbot_def.dict()
        
        # ChatbotDef 객체 속성 추출 (Fallback)
        result = {"id": getattr(chatbot_def, 'id', '')}
        if hasattr(chatbot_def, 'name'):
            result['name'] = chatbot_def.name
        if hasattr(chatbot_def, 'description'):
            result['description'] = chatbot_def.description
        if hasattr(chatbot_def, 'capabilities'):
            cap = chatbot_def.capabilities
            if hasattr(cap, 'model_dump'):
                result['capabilities'] = cap.model_dump()
            elif hasattr(cap, 'dict'):
                result['capabilities'] = cap.dict()
            else:
                result['capabilities'] = cap
        if hasattr(chatbot_def, 'sub_chatbots'):
            result['sub_chatbots'] = chatbot_def.sub_chatbots
        if hasattr(chatbot_def, 'retrieval'):
            ret = chatbot_def.retrieval
            if hasattr(ret, 'model_dump'):
                result['retrieval'] = ret.model_dump()
            elif hasattr(ret, 'dict'):
                result['retrieval'] = ret.dict()
            else:
                result['retrieval'] = ret
        
        return result
    
    def create_function_tool(self, chatbot_id: str, router_instance=None):
        """
        JSON → Agent → FunctionTool 변환 (직접 실행 경로)

        AgentTool 대신 FunctionTool을 사용하여 child agent를 명시적으로 실행하고
        결과를 문자열로 반환. Tool calling 메시지 경로 문제를 우회.

        Args:
            chatbot_id: 챗봇 ID
            router_instance: DelegationRouter 인스턴스 (run_async_with_debug 사용용)

        Returns:
            FunctionTool 인스턴스 또는 None
        """
        if not ADK_AVAILABLE or FunctionTool is None:
            logger.error("[SubAgentFactory] FunctionTool not available")
            return None

        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            logger.warning(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
            return None

        # Build a synchronous wrapper that calls the child agent
        def _run_child(request: str) -> str:
            """Execute child agent and return its output."""
            logger.warning(f"[DELEGATE_START] {chatbot_id} request={request[:200]}")

            import asyncio
            try:
                # Try to get existing event loop
                loop = asyncio.get_running_loop()
                # Already in async context - use thread executor
                logger.warning(f"[DELEGATE_WARN] {chatbot_id} called inside running loop, using run_in_executor")
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_child_async, chatbot_id, request)
                    result = future.result(timeout=120)
                    return result
            except RuntimeError:
                # No running loop - safe to use asyncio.run
                result = asyncio.run(self._run_child_async(chatbot_id, request))
                return result

        # Set function metadata for ADK to pick up
        safe_name = chatbot_id.replace("-", "_")
        _run_child.__name__ = safe_name
        _run_child.__doc__ = chatbot_def.get("description", f"Delegate to {chatbot_id}")

        tool = FunctionTool(func=_run_child)
        logger.info(f"[SubAgentFactory] Created FunctionTool for {chatbot_id} (name={safe_name})")
        return tool

    async def _run_child_async(self, chatbot_id: str, request: str) -> str:
        """Async helper to run child agent and return output."""
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import InMemorySessionService
        from google.genai import types

        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            return f"[ERROR] Chatbot not found: {chatbot_id}"

        # Create child agent
        child_agent = self.create_agent(chatbot_def)
        if not child_agent:
            return f"[ERROR] Failed to create agent: {chatbot_id}"

        # Setup runner with fresh session
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=f"child_{chatbot_id}",
            agent=child_agent,
            session_service=session_service,
        )
        session_id = f"child_{chatbot_id}_{int(time.time())}"
        user_id = "delegate_user"

        content = types.Content(role='user', parts=[types.Part(text=request)])

        full_response = []
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            full_response.append(part.text)

            result = "".join(full_response)
            logger.warning(f"[DELEGATE_END] {chatbot_id} result_preview={result[:500]}")
            return result if result else "[ERROR] Child agent returned empty response"
        except Exception as e:
            logger.error(f"[DELEGATE_ERROR] {chatbot_id}: {e}", exc_info=True)
            return f"[ERROR] {chatbot_id} execution failed: {e}"

    def clear_cache(self):
        """에이전트 캐시 초기화"""
        self._agent_cache.clear()
        logger.info("[SubAgentFactory] Cache cleared")
    
    def create_agent_tool(self, chatbot_id: str) -> Optional[Any]:
        """
        JSON → Agent → FunctionTool 변환 (ThreadPoolExecutor 격리 실행)
        
        FunctionTool을 사용하고, 내부에서 ThreadPoolExecutor로
        완전히 격리된 스레드에서 비동기 Agent를 실행합니다.
        이 방식으로 event loop 충돌을 피할 수 있습니다.
        
        Args:
            chatbot_id: 챗봇 ID
            
        Returns:
            FunctionTool 인스턴스 또는 None
        """
        if not ADK_AVAILABLE or FunctionTool is None:
            logger.error("[SubAgentFactory] ADK or FunctionTool not available")
            return None
        
        # JSON 정의 로드
        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            logger.warning(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
            return None
        
        # JSON → Agent 생성
        agent = self.create_agent(chatbot_def)
        if not agent:
            logger.warning(f"[SubAgentFactory] Failed to create agent for {chatbot_id}")
            return None
        
        # Agent → FunctionTool 변환 (ThreadPoolExecutor 격리)
        import concurrent.futures
        
        def _invoke_subagent(request: str) -> str:
            """하위 Agent를 실행하고 text 응답을 수집합니다."""
            try:
                from google.adk.runners import Runner
                from google.adk.sessions import InMemorySessionService
                from google.genai import types
                import asyncio
                
                logger.info(f"[SubAgentFactory] Invoking sub-agent {chatbot_id} with request: {request[:200]}...")
                
                async def _run_async():
                    session_service = InMemorySessionService()
                    runner = Runner(
                        agent=agent, 
                        app_name=chatbot_id, 
                        session_service=session_service
                    )
                    session = await session_service.create_session(
                        app_name=chatbot_id, 
                        user_id="subagent",
                        state={}
                    )
                    
                    content = types.Content(
                        role='user', 
                        parts=[types.Part(text=request)]
                    )
                    
                    full_response = []
                    
                    async for event in runner.run_async(
                        user_id="subagent",
                        session_id=session.id,
                        new_message=content
                    ):
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    full_response.append(part.text)
                    
                    return "".join(full_response)
                
                def _thread_target():
                    """새 스레드에서 새 event loop로 실행"""
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(_run_async())
                    finally:
                        loop.close()
                
                # 메인 스레드에 이미 event loop가 있으면 새 스레드에서 실행
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(_thread_target)
                            return future.result(timeout=60)
                    else:
                        return loop.run_until_complete(_run_async())
                except RuntimeError:
                    # 루프가 없으면 직접 실행
                    return asyncio.run(_run_async())
                
            except Exception as e:
                logger.error(f"[SubAgentFactory] Sub-agent {chatbot_id} error: {e}", exc_info=True)
                return f"[하위 Agent 실행 오류: {e}]"
        
        _invoke_subagent.__name__ = chatbot_id.replace("-", "_")
        _invoke_subagent.__doc__ = f"{chatbot_def.get('name', chatbot_id)}에게 위임합니다."
        
        try:
            tool = FunctionTool(func=_invoke_subagent)
            logger.info(f"[SubAgentFactory] Created FunctionTool for {chatbot_id} (ThreadPoolExecutor)")
            return tool
        except Exception as e:
            logger.error(f"[SubAgentFactory] Failed to create FunctionTool: {e}")
            return None

    def create_root_agent_with_tools(self, chatbot_id: str) -> Optional[Any]:
        """
        Root Agent + 하위 Agent Tools 생성
        
        Args:
            chatbot_id: Root 챗봇 ID
            
        Returns:
            Agent 인스턴스 (tools에 하위 Agent들이 등록됨) 또는 None
        """
        if not ADK_AVAILABLE:
            logger.error("[SubAgentFactory] ADK not available")
            return None
        
        # 챗봇 정의 로드
        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            logger.error(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
            # 추가 디버그: 사용 가능한 챗봇 목록 출력
            available = list(self._chatbot_defs.keys())
            if self._chatbot_manager:
                available = [c.id for c in self._chatbot_manager.list_all()]
            logger.error(f"[SubAgentFactory] Available chatbots: {available}")
            return None
        
        capabilities = chatbot_def.get("capabilities", {})
        policy = chatbot_def.get("policy", {})
        sub_chatbots = chatbot_def.get("sub_chatbots", [])
        
        # 하위 챗봘을 Tool로 변환
        tools = []
        for sub in sub_chatbots:
            # SubChatbotRef 객체 지원 (.id 속성)
            if hasattr(sub, 'id'):
                sub_id = sub.id
            elif isinstance(sub, dict):
                sub_id = sub.get("id")
            else:
                sub_id = None
            
            if sub_id:
                sub_tool = self.create_agent_tool(sub_id)
                if sub_tool:
                    tools.append(sub_tool)
                    logger.info(f"[SubAgentFactory] Added {sub_id} as tool to {chatbot_id}")
        
        # Root 자신의 db_ids 기반 RAG tool 추가
        db_ids = _extract_db_ids(chatbot_def)
        has_rag_tool = False
        if db_ids:
            rag_tool = self._build_rag_tool(chatbot_id, db_ids)
            if rag_tool:
                tools.append(rag_tool)
                has_rag_tool = True
                logger.info(f"[SubAgentFactory] Added root RAG tool to {chatbot_id} (dbs: {db_ids})")
        
        # 시스템 프롬프트 구성
        system_prompt = self._build_system_prompt(chatbot_def, has_rag_tool)
        
        # RAG 기반 답변 시 출처 명시 지시
        system_prompt += "\n\n[출처 명시 규칙]\n"
        system_prompt += "답변 시 참고한 문서의 출처(데이터베이스 ID, 문서 제목 등)를 명확히 표시해주세요.\n"
        system_prompt += "예시: '이 내용은 [출처: db_hr_policy] 문서를 참고하였습니다.' 또는 '참고: db_tech_overview'\n"
        system_prompt += "여러 출처를 참고한 경우 모든 출처를 나열해주세요.\n"
        
        # [출처 명시 규칙] 바로 아래에 RAG tool 사용 지시 추가
        if has_rag_tool:
            system_prompt += """
[RAG 검색 도구 사용 규칙 - 반드시 준수]
1. 질문에 답하기 전, 반드시 rag_search 도구를 사용하여 관련 문서를 검색하세요
2. 검색 결과 없이 추측하여 답변하지 마세요
3. 검색 결과가 없으면 '해당 질문에 대한 문서가 없습니다'라고 답변하세요
4. 답변은 검색된 문서 내용에만 기반하여 작성하세요
"""
        
        if sub_chatbots:
            sub_info = self._format_sub_chatbots_for_tools(sub_chatbots)
            system_prompt += f"\n\n[사용 가능한 하위 전문가 도구]\n{sub_info}\n\n"
            system_prompt += "사용자 질문에 따라 적절한 도구를 호출하세요. 도구를 호출하면 자동으로 해당 전문가에게 위임됩니다."
        
        # Root Agent 생성 (tools 포함)
        try:
            # ADK Agent 이름은 유효한 식별자여야 함 (하이픈 -> 언더스코어)
            agent_name = chatbot_id.replace("-", "_")
            
            # tools가 빈 리스트면 None 대신 빈 리스트를 그대로 전달하거나 생략
            agent_kwargs = dict(
                name=agent_name,
                model=self.model,
                description=chatbot_def.get("description", ""),
                instruction=system_prompt,
                output_key=f"{chatbot_id}_response"
            )
            if tools:
                agent_kwargs["tools"] = tools
            
            root_agent = Agent(**agent_kwargs)
            logger.info(f"[SubAgentFactory] Created root agent {agent_name} with {len(tools)} tools")
            return root_agent
        except Exception as e:
            logger.error(f"[SubAgentFactory] Failed to create root agent: {e}")
            return None
    
    def _format_sub_chatbots_for_tools(self, sub_chatbots: List[Dict]) -> str:
        """하위 챗봘 목록을 Tool 설명용으로 포맷팅"""
        lines = []
        for sub in sub_chatbots:
            sub_id = self._get_sub_id(sub)
            sub_def = self._get_chatbot_def(sub_id)
            if sub_def:
                desc = sub_def.get("description", "")
                lines.append(f"- {sub_id}: {desc}")
        return "\n".join(lines) if lines else "(하위 전문가 없음)"


# 전역 팩토리 인스턴스
_factory: Optional[SubAgentFactory] = None


def get_factory() -> SubAgentFactory:
    """팩토리 싱글톤 반환"""
    global _factory
    if _factory is None:
        _factory = SubAgentFactory()
    return _factory
