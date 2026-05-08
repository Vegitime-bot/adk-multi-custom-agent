# 🔒 위임(Delegation) 시스템 - 수정 금지 가이드

> **작성일:** 2026-05-08  
> **검증 상태:** 사내 실제 서버에서 정상 동작 확인 완료  
> **커밋:** `90d3d49` (main 브랜치)  
> **핵심 원칙:** 이 문서에 기록된 위임 관련 구조를 수정하면 시스템이 깨질 수 있습니다. 수정이 필요하면 이 문서를 먼저 읽고, 사내 담당자와 반드시 상의하세요.

---

## 📋 전체 흐름 요약

```
사용자 질문
  ↓
Parent Agent (pddi_total)
  ├─ 일반 질문 → 직접 RAG 검색 → 답변
  └─ 주간보고/회의록 질문 → 하위 AgentTool 호출 (pddi_minutes)
                                                ↓
                                      Child Agent (pddi_minutes)
                                        ├─ 내부 RAG tool로 문서 검색
                                        └─ 검색 결과 기반 답변 생성
```

---

## 🎯 핵심 문제 해결 역사

### 원래 문제 (2026-05-07 이전)
- **Child 단독 실행:** RAG 검색 → 답변 ✅
- **Parent → Child 위임 (AgentTool):** Child 내부에 RAG tool 없음 → 환각/실패 ❌

### 원인
`create_agent_tool()`로 AgentTool 생성 시, 내부 `create_agent()`가 db_ids를 못 읽어서 RAG tool이 생성되지 않았음.

### 해결 (2026-05-08, `90d3d49`)
6개 수정사항 반영 → 사내 서버에서 정상 동작 확인.

---

## 📁 수정된 파일 2개

### 1. `adk_agents/sub_agent_factory.py`

#### 수정 1: `_extract_db_ids()` (모듈 레벨 함수)
- 위치: `SubAgentFactory` 클래스 **앞** (모듈 레벨)
- 역할: `dict`, `Pydantic 객체` 두 구조 모두에서 `db_ids` 추출
- **중요:** `hasattr(retrieval, 'db_ids')`를 `isinstance(retrieval, dict)`보다 먼저 체크

```python
def _extract_db_ids(chatbot_def: Dict[str, Any]) -> List[str]:
    caps = chatbot_def.get("capabilities", {})
    if caps and isinstance(caps, dict):
        db_ids = caps.get("db_ids", [])
        if db_ids: return db_ids

    retrieval = chatbot_def.get("retrieval")
    if retrieval:
        if hasattr(retrieval, 'db_ids'):
            return list(retrieval.db_ids)
        elif isinstance(retrieval, dict):
            db_ids = retrieval.get("db_ids", [])
            if db_ids: return db_ids

    if hasattr(chatbot_def, 'capabilities'):
        caps = chatbot_def.capabilities
        if hasattr(caps, 'db_ids'):
            return list(caps.db_ids)

    return []
```

#### 수정 2: `create_agent()` 메서드
- `_extract_db_ids()` 호출 → `has_rag_tool` 플래그 설정
- `has_rag_tool=True`면 `_build_rag_tool()` 호출 → `agent_kwargs["tools"]`에 추가
- `Agent(**agent_kwargs)` 생성 시 tools 자동 주입

```python
def create_agent(self, chatbot_def: Dict[str, Any]) -> Agent:
    chatbot_id = chatbot_def["id"]
    agent_name = chatbot_id.replace("-", "_")
    if chatbot_id in self._agent_cache: return self._agent_cache[chatbot_id]

    db_ids = _extract_db_ids(chatbot_def)   # ← 핵심
    has_rag_tool = len(db_ids) > 0
    system_prompt = self._build_system_prompt(chatbot_def, has_rag_tool)

    tools = []
    if has_rag_tool:
        rag_tool = self._build_rag_tool(chatbot_id, db_ids)
        if rag_tool: tools.append(rag_tool)

    agent_kwargs = dict(name=agent_name, model=self.model,
                        instruction=system_prompt,
                        description=chatbot_def.get("description", ""))
    if tools: agent_kwargs["tools"] = tools

    agent = Agent(**agent_kwargs)
    self._agent_cache[chatbot_id] = agent
    return agent
```

#### 수정 3: `_build_rag_tool()` 메서드
- 위치: `create_agent()` **바로 아래**
- `FunctionTool(func=rag_search)` 생성
- `rag_search.name = f"rag_search_{chatbot_id.replace('-', '_')}"`
- `rag_search.doc = "Retrieve relevant documents..."`

**⚠️ 주의:** 이 메서드 이름이 기존 코드에도 `_build_rag_tool`이었으나, 이 버전으로 **완전히 치환**된 상태. 기존 버전(499번 라인)은 제거됨.

#### 수정 4: `_build_system_prompt()`
- 시그니처: `def _build_system_prompt(self, chatbot_def, has_rag_tool: bool = False)`
- **Parent (`has_subs=True`):** `delegation_prompt` 끝에 RAG 지시 추가
  - "직접 답변하기 전 rag_search 도구 사용"
  - "검색 결과 없으면 하위 전문가에게 위임"
- **Leaf (`has_subs=False`):** `leaf_prompt` 끝에 RAG 지시 추가
  - "반드시 rag_search 도구 사용"
  - "추측 금지, 검색 결과 기반 답변"

#### 수정 5: `create_root_agent_with_tools()`
- 하위 AgentTool 생성 루프 **바로 아래**에 추가:
  ```python
  db_ids = _extract_db_ids(chatbot_def)
  if db_ids:
      rag_tool = self._build_rag_tool(chatbot_id, db_ids)
      if rag_tool:
          tools.append(rag_tool)
          has_rag_tool = True
  ```
- `[출처 명시 규칙]` **바로 아래**에 RAG tool 사용 지시 추가

---

### 2. `adk_agents/delegation_router_agent/__init__.py`

#### 수정 6: `route_and_stream_with_tools()`

**핵심 변경 1: Leaf agent RAG 컨텍스트 스킵**
```python
chatbot_def = self._load_chatbot_def(chatbot_id)
has_sub_chatbots = bool(chatbot_def and getattr(chatbot_def, 'sub_chatbots', None))
is_leaf_agent = not has_sub_chatbots   # ← 추가

if rag_results:
    if is_leaf_agent:
        # Leaf: 자신의 RAG tool이 있으므로 컨텍스트 주입 스킵
        message_with_context = message
    elif has_sub_chatbots and self._is_weekly_report_query(message):
        # Parent + 주간보고: RAG 생략, tool calling 유도
        message_with_context = message
    else:
        # 기존 RAG 컨텍스트 주입 로직
        ...
```

**핵심 변경 2: 이벤트 루프에서 function 결과 노출 방지**
- `function_call` 감지: `yield` 금지, **로그만**
- `function_response` 감지: `yield` + `append` 금지, **로그만**
- `invocation_results` 감지: `yield` + `append` 금지, **로그만**
- **원리:** ADK Runner가 도구 호출 후 최종 답변을 text chunk로 돌려줌. text만 스트리밍하면 됨.

```python
# ❌ 잘못된 방식 (이전 AI 버전)
tool_info = f"[도구 호출: {part.function_call.name}]"
yield self._sse_data(tool_info)   # ← 사용자 화면에 노출됨

# ✅ 올바른 방식 (현재 작동 버전)
logger.info(f"Tool call: {part.function_call.name}")
# yield 없음 - 내부 처리용
```

---

## 🚫 절대 하지 말 것

| 행동 | 결과 |
|------|------|
| `_extract_db_ids()` 순서 바꾸기 | Pydantic 객체 처리 실패, RAG tool 미생성 |
| `function_call`에 `yield` 추가 | 사용자 화면에 "[도구 호출: ...]" 노출 |
| `function_response`에 `yield` 추가 | 사용자 화면에 raw 검색 결과 노출 |
| `invocation_results`에 `yield` 추가 | 중복 결과 노출 |
| `_build_rag_tool` 두 개 두기 | 이름 충돌, 어떤 게 쓰일지 불명확 |
| Parent/Leaf RAG 프롬프트를 분리하지 않고 통합 | Parent가 하위 위임 안 하고 자신의 RAG만 검색 |
| `is_leaf_agent` 선언 누락 | `NameError` 또는 잘못된 RAG 주입 |

---

## 📎 참조 문서

- `REVISION_GUIDE.md` - 6개 수정사항 원문
- `ROUTER_FIX.md` - route_and_stream_with_tools() 이벤트 루프 수정 가이드
- `docs/PHASE3_PLAN.md` - Phase 3 계획 (위임 시스템 개선 예정 사항)

---

## ✅ 수정이 필요하면

1. 이 문서(`DELEGATION_LOCK.md`)를 먼저 읽을 것
2. `REVISION_GUIDE.md`, `ROUTER_FIX.md`와 교차 검증
3. Mock 테스트(`test_rag_verification.py`) 돌려보기
4. **사내 실제 서버에서 반드시 테스트 후 푸시**
5. 불확실하면 담당자(@youngdong jang)와 상의

---

_마지막 확인: 2026-05-08 16:27 KST_  
_정상 동작 커밋: `90d3d49`_
