# ADK Multi Custom Agent - 수정 지침서
## 파일 1: adk_agents/sub_agent_factory.py

### 1) _extract_db_ids() 함수 (SubAgentFactory 클래스 앞)
```python
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
```

### 2) create_agent() 메서드 전체
```python
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
```

### 3) _build_rag_tool() 메서드 (create_agent() 바로 아래)
```python
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
```

### 4) _build_system_prompt() 수정
- 시그니처: `def _build_system_prompt(self, chatbot_def, has_rag_tool: bool = False) -> str:`
- if has_subs: 블록 끝에 RAG 지시 추가
- else: (leaf) 블록에 RAG 지시 추가

### 5) create_root_agent_with_tools() 내 RAG tool 추가
- sub_chatbots tool 생성 루프 바로 아래에 db_ids 기반 RAG tool 추가
- system_prompt 구성 후 RAG tool 사용 지시 추가

## 파일 2: adk_agents/delegation_router_agent/__init__.py

### 6) route_and_stream_with_tools() RAG 컨텍스트 주입 로직 수정
- `is_leaf_agent = not has_sub_chatbots` 추가
- `if rag_results:` 블록 내에서 leaf agent 스킵 조건 추가
