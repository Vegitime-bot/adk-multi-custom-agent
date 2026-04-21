# 02. 시스템 아키텍처 (Architecture)

## 전체 시스템 구성

```
┌─────────────────────────────────────────────────────────┐
│                     클라이언트                            │
│         브라우저 (챗봇 UI / 관리자 패널)                   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼────────────────────────────────┐
│              Multi Custom Agent Server                   │
│                  FastAPI (port 8080)                     │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Chat API   │  │  Admin API   │  │  Permissions  │  │
│  │ /api/chat   │  │ /admin/api/* │  │  /api/perms   │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
│         │                                               │
│  ┌──────▼──────────────────────────────────────────┐   │
│  │              실행 파이프라인                       │   │
│  │  Auth → Permission → Session → Factory → Exec   │   │
│  └──────┬──────────────────────────────────────────┘   │
│         │                                               │
│  ┌──────▼───────────────────────────────────────────┐  │
│  │              Executor 계층                        │  │
│  │  ToolExecutor / AgentExecutor /                  │  │
│  │  HierarchicalAgentExecutor                       │  │
│  └──────┬───────────────────────────────────────────┘  │
│         │                                               │
│  ┌──────▼──────────┐  ┌───────────────────────────────┐│
│  │  IngestionClient│  │       LLM Client              ││
│  │  (RAG 검색)     │  │  (OpenAI SDK, Streaming)      ││
│  └──────┬──────────┘  └──────────────┬────────────────┘│
└─────────┼──────────────────────────┼─────────────────-─┘
          │                          │
┌─────────▼──────────┐  ┌───────────▼────────────┐
│  Ingestion Server  │  │      LLM Server        │
│  (Vector Search)   │  │  (OpenAI-compatible)   │
│  port: 8001        │  │  e.g. GLM4.7, kimi     │
└────────────────────┘  └────────────────────────┘
          │
┌─────────▼──────────┐
│    PostgreSQL      │
│  (선택, 권한/대화)  │
│  port: 5432        │
└────────────────────┘
```

---

## 핵심 설계 원칙

### 1. 멀티 테넌트 격리
- 챗봇마다 독립적인 DB 범위 (`db_ids`), 시스템 프롬프트, 권한
- 메모리 키: `(chatbot_id, session_id)` → 챗봇/세션 간 데이터 혼용 없음
- 사용자는 권한 있는 챗봇의 `authorized_db_ids`만 검색 가능

### 2. 팩토리 메서드 패턴
- `create_execution_context()`: 런타임에 `ExecutionContext` 조합
  - 챗봇 정의 + 세션 + 사용자 권한 → 실행 컨텍스트
  - `authorized_db_ids = chatbot_scope ∩ user_scope`

### 3. 전략 패턴 (Executor)
- `ExecutionRole`에 따라 실행 엔진 교체
- `TOOL`: `ToolExecutor` (무상태)
- `AGENT`: `AgentExecutor` (대화형)
- `AGENT` + sub_chatbots: `HierarchicalAgentExecutor` (계층적)

### 4. 선언적 챗봇 등록
- `chatbots/*.json` 파일만 추가하면 챗봇 자동 등록
- 코드 변경 불필요

---

## 컴포넌트 다이어그램

```
app.py (FastAPI)
├── app.state.chatbot_manager     ← chatbots/*.json 로드
├── app.state.session_manager     ← 세션 수명주기
├── app.state.memory_manager      ← 대화 히스토리
├── app.state.ingestion_client    ← 외부 RAG 서버 클라이언트
└── app.state.role_router         ← Executor 선택 라우터

backend/
├── api/
│   ├── chat.py          ← POST /api/chat (SSE)
│   ├── admin.py         ← 챗봇 CRUD
│   ├── permissions.py   ← 접근 제어 CRUD
│   ├── conversations.py ← 대화 기록 조회
│   ├── sso.py           ← SSO 콜백 처리
│   ├── health.py        ← 헬스체크
│   └── deps.py          ← FastAPI 의존성 주입
│
├── core/
│   ├── models.py        ← ChatbotDef, ExecutionContext, Message, ChatSession
│   └── factory.py       ← create_execution_context()
│
├── managers/
│   ├── chatbot_manager.py   ← JSON CRUD, 계층 검증
│   ├── session_manager.py   ← 세션 생성/조회
│   └── memory_manager.py    ← (chatbot_id, session_id) 키 대화 메모리
│
├── executors/
│   ├── base_executor.py              ← RAG/LLM 공통 로직
│   ├── tool_executor.py              ← 무상태 단일 호출
│   ├── agent_executor.py             ← 대화형 메모리 유지
│   ├── parent_agent_executor.py      ← (deprecated) 2단계 계층
│   └── hierarchical_agent_executor.py ← 3단계 계층 + 상향 위임
│
├── roles/
│   ├── base.py          ← BaseRoleHandler 인터페이스
│   ├── tool_handler.py
│   ├── agent_handler.py
│   └── router.py        ← ExecutionRole → Handler 매핑
│
├── retrieval/
│   └── ingestion_client.py  ← POST /search 호출
│
├── llm/
│   └── client.py            ← OpenAI SDK 스트리밍
│
├── permissions/
│   └── repository.py        ← Mock / PostgreSQL 구현
│
├── conversation/
│   └── repository.py        ← 대화 로그 저장/조회
│
├── database/
│   └── session.py           ← SQLAlchemy 엔진, 세션
│
└── auth/
    └── mock_auth.py         ← Mock 인증 (knox_id: "user-001")
```

---

## 데이터 흐름 (Chat API)

```
POST /api/chat
{
  "chatbot_id": "chatbot-hr",
  "message": "연차 신청은?",
  "session_id": "sess-abc",   // 선택
  "mode": "agent"              // 선택 (override)
}

Step 1: 인증
  └─ USE_MOCK_AUTH=true  → knox_id = "user-001"
  └─ USE_MOCK_AUTH=false → SSO 세션에서 knox_id 추출

Step 2: 챗봇 조회
  └─ ChatbotManager.get_active("chatbot-hr") → ChatbotDef

Step 3: 권한 확인
  └─ PermissionRepository.check_access(knox_id, chatbot_id) → bool

Step 4: 세션 처리
  └─ SessionManager.get_or_create(knox_id, chatbot_id) → ChatSession

Step 5: 실행 컨텍스트 생성 (Factory Method)
  └─ authorized_db_ids = chatbot.db_ids ∩ user.db_scope
  └─ effective_role = session.override ?? chatbot.default_role
  └─ history = MemoryManager.get_history(chatbot_id, session_id)
  └─ → ExecutionContext

Step 6: Executor 선택 및 실행
  └─ TOOL → ToolExecutor.execute(ctx, message)
  └─ AGENT (leaf) → AgentExecutor.execute(ctx, message)
  └─ AGENT (has sub_chatbots) → HierarchicalAgentExecutor.execute(ctx, message)

Step 7: Executor 내부 처리
  └─ IngestionClient.search(authorized_db_ids, query, k=5)
  └─ confidence = calculate_confidence(search_results)
  └─ confidence < threshold? → 위임 또는 직접 답변
  └─ build_messages(system_prompt, context, history, user_message)
  └─ LLMClient.stream_chat(messages) → yield chunks

Step 8: SSE 스트리밍 응답
  └─ "data: {chunk}\n\n" × N
  └─ MemoryManager.append_pair(chatbot_id, session_id, user_msg, assistant_msg)
  └─ ConversationRepository.save(log)
```

---

## 계층적 위임 아키텍처

### 3단계 계층 예시

```
chatbot-company (root, level 0)
├── chatbot-hr (level 1)
│   ├── chatbot-hr-policy (level 2, leaf)
│   └── chatbot-hr-benefit (level 2, leaf)
└── chatbot-tech (level 1)
    ├── chatbot-tech-backend (level 2, leaf)
    ├── chatbot-tech-frontend (level 2, leaf)
    └── chatbot-tech-devops (level 2, leaf)
```

### 위임 결정 로직

```
신뢰도 계산:
  - 검색 결과 수 / 기대 결과 수 × 40
  - 평균 유사도 점수 × 60
  = 0~100 신뢰도

하위 위임 (downward):
  신뢰도 < delegation_threshold(70)
  → 하이브리드 스코어링으로 최적 하위 챗봇 선택
    (키워드 매칭 + 임베딩 기반 스코어)
  → max_parallel_subs(2) 병렬 실행
  → 응답 합성

상향 위임 (upward, enable_parent_delegation=true):
  하위 챗봇에서도 신뢰도 낮음
  → parent_id로 상위 챗봇에 컨텍스트 전달
  → 상위에서 재처리
```

---

## 상태 관리 전략

| 컴포넌트 | 상태 유형 | 저장소 |
|---------|----------|--------|
| ChatbotManager | 챗봇 정의 | 메모리 (chatbots/*.json에서 로드) |
| SessionManager | 세션 | 메모리 (향후 Redis 교체 가능) |
| MemoryManager | 대화 히스토리 | 메모리 (향후 Redis 교체 가능) |
| PermissionRepository | 접근 권한 | Mock(메모리) / PostgreSQL |
| ConversationRepository | 대화 로그 | Mock(메모리) / PostgreSQL |

---

## 확장 포인트

| 포인트 | 방법 |
|--------|------|
| 새 챗봇 추가 | `chatbots/` 디렉토리에 JSON 파일 추가 |
| 새 Executor | `BaseExecutor` 상속, `execute()` 구현 |
| 실제 DB | `USE_MOCK_DB=false` + PostgreSQL 연결 설정 |
| SSO 연동 | `USE_MOCK_AUTH=false` + SSO 환경변수 설정 |
| 분산 세션 | SessionManager/MemoryManager → Redis 구현으로 교체 |
| 새 LLM | `LLM_BASE_URL` 변경 (OpenAI 호환 엔드포인트면 무관) |
