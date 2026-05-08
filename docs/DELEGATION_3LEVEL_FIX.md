# 3단계 위임 이슈 분석 및 수정 방향

## 문제 요약

Level 0(lsibusiness) → Level 1(pddi_total) → Level 2(pddi_minutes) 위임 체인이 끊김.

## 현재 동작 흐름

```
[사용자 질문: 52주차 주간보고 정리해줘]
  ↓
Level 0: lsibusiness Root Agent
  ├─ tools: [pddi_total_AgentTool, rag_search_lsibusiness]
  ↓ LLM이 pddi_total_AgentTool 호출
Level 1: pddi_total Agent (AgentTool로 생성됨)
  ├─ tools: [rag_search_pddi_total]   ← ❌ pddi_minutes 없음!
  ↓ LLM이 주간보고 질문 → 위임할 도구 없음
  FAIL-CLOSED: "pddi_minutes 도구 호출이 필요한데 호출되지 않았습니다"
```

## 원인

`create_agent_tool("pddi_total")` 내부:

```python
def create_agent_tool(self, chatbot_id):
    chatbot_def = self._get_chatbot_def(chatbot_id)  # pddi_total 정의
    agent = self.create_agent(chatbot_def)            # ← 여기가 문제
    tool = AgentTool(agent=agent)
    return tool
```

`create_agent(chatbot_def)` 내부:

```python
def create_agent(self, chatbot_def):
    # db_ids 기반 RAG tool만 추가
    # sub_chatbots는 무시됨 ← ❌
```

**핵심:** `create_agent()`는 `sub_chatbots`를 tools로 등록하지 않음.  
반면 `create_root_agent_with_tools()`는 sub_chatbots를 tools로 등록함.

## 수정 방향

### 방법 A: `create_agent()`에 sub_chatbots 등록 추가 (권장)

`create_agent()` 메서드에 sub_chatbots → tools 변환 로직 추가:

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

    # 1. RAG tool 추가 (기존과 동일)
    if has_rag_tool:
        rag_tool = self._build_rag_tool(chatbot_id, db_ids)
        if rag_tool:
            tools.append(rag_tool)
            logger.info(f"[SubAgentFactory] Added RAG search tool for {chatbot_id}")

    # 2. 하위 챗봘을 AgentTool로 변환하여 추가 (★ 신규)
    sub_chatbots = chatbot_def.get("sub_chatbots", [])
    for sub in sub_chatbots:
        sub_id = self._get_sub_id(sub)
        if sub_id:
            sub_tool = self.create_agent_tool(sub_id)  # 재귀적으로 하위 생성
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
    logger.info(f"[SubAgentFactory] Created agent {chatbot_id} with {len(tools)} tools (rag={has_rag_tool}, subs={len(sub_chatbots)})")
    return agent
```

**효과:**
- pddi_total 생성 시:
  - tools: [rag_search_pddi_total, pddi_minutes_AgentTool]
- lsibusiness → pddi_total 위임 후:
  - pddi_total이 주간보고 질문 → pddi_minutes_AgentTool 호출 가능

### 방법 B: `create_agent_tool()`에서 sub_chatbots 직접 처리

`create_agent()`는 leaf agent용으로 두고, `create_agent_tool()`에서 별도로 sub_chatbots를 추가:

```python
def create_agent_tool(self, chatbot_id: str) -> Optional[Any]:
    chatbot_def = self._get_chatbot_def(chatbot_id)
    if not chatbot_def: return None

    # 1. 하위 챗봘을 미리 tools로 변환
    tools = []
    for sub in chatbot_def.get("sub_chatbots", []):
        sub_id = self._get_sub_id(sub)
        if sub_id:
            sub_tool = self.create_agent_tool(sub_id)  # 재귀
            if sub_tool: tools.append(sub_tool)

    # 2. 현재 챗봘 agent 생성 (has_rag_tool 포함)
    agent = self.create_agent(chatbot_def)  # 기존 방식 유지

    # 3. agent에 하위 tools 추가
    if tools and not hasattr(agent, 'tools') or agent.tools is None:
        agent.tools = tools
    elif tools:
        agent.tools.extend(tools)

    tool = AgentTool(agent=agent)
    return tool
```

**단점:** agent의 tools를 직접 조작해야 해서 깔끔하지 않음.

---

## 권장: 방법 A

**이유:**
- `create_agent()`가 챗봇 정의를 완전히 반영하도록 만듦
- `create_root_agent_with_tools()`와 일관된 동작
- 재귀 구조로 자연스러운 중첩 위임 지원

## 주의사항

1. **순환 참조 방지:** 챗봇 정의에 순환 sub_chatbots가 없어야 함
2. **캐시 전략:** `create_agent_tool()`이 `create_agent()`를 호출하고, `create_agent()`가 `create_agent_tool()`을 호출하므로 캐시로 무한 재귀 방지
3. **LLM 컨텍스트:** 3단계 tools가 많아지면 tool description 길이 초과 가능성 → description을 간결하게

---

## 테스트 체크리스트

- [ ] Level 0(lsibusiness) → Level 1(pddi_total) 위임
- [ ] Level 1(pddi_total) → Level 2(pddi_minutes) 위임
- [ ] Level 2(pddi_minutes)가 내부 RAG tool로 문서 검색
- [ ] 최종 답변에 실제 주간보고 내용 반영
- [ ] 중간 도구 호출 과정이 사용자 화면에 노출되지 않음
