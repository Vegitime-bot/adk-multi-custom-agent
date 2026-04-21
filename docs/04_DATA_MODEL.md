# 04. 데이터 모델 (Data Model)

## 1. PostgreSQL 스키마

> 소스: `database/schema.sql`, `database/schema_conversation.sql`

### 1.1 test.user_chatbot_access (접근 권한)

```sql
CREATE TABLE test.user_chatbot_access (
    id         SERIAL      NOT NULL PRIMARY KEY,
    knox_id    VARCHAR(50) NULL,         -- 사용자 Knox ID
    chatbot_id VARCHAR(50) NULL,         -- 챗봇 ID
    can_access BOOLEAN     DEFAULT TRUE, -- 접근 권한 여부
    created_at TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_chatbot UNIQUE (knox_id, chatbot_id)
);

CREATE INDEX idx_user_chatbot_knox_id   ON test.user_chatbot_access(knox_id);
CREATE INDEX idx_user_chatbot_chatbot_id ON test.user_chatbot_access(chatbot_id);
```

**관계도:**

```
knox_id (사용자) ─── N:M ─── chatbot_id (챗봇)
                   (can_access)
```

**샘플 데이터:**

| knox_id | chatbot_id | can_access |
|---------|-----------|------------|
| user-001 | chatbot-hr | true |
| user-001 | chatbot-tech | true |
| user-002 | chatbot-hr | true |
| user-002 | chatbot-tech | false |
| user-003 | chatbot-hr | false |
| user-003 | chatbot-tech | true |

---

### 1.2 test.conversation_logs (대화 기록)

```sql
CREATE TABLE test.conversation_logs (
    id                   SERIAL       PRIMARY KEY,
    session_id           VARCHAR(100) NOT NULL,  -- 대화 세션 ID
    knox_id              VARCHAR(50)  NOT NULL,  -- 사용자 Knox ID
    chatbot_id           VARCHAR(50)  NOT NULL,  -- 챗봇 ID
    user_message         TEXT         NOT NULL,  -- 사용자 메시지
    assistant_response   TEXT         NOT NULL,  -- 어시스턴트 응답
    tokens_used          INTEGER      DEFAULT 0, -- 사용된 토큰 수
    latency_ms           INTEGER      DEFAULT 0, -- 응답 지연시간 (ms)
    search_results_count INTEGER      DEFAULT 0, -- RAG 검색 결과 수
    confidence_score     FLOAT        DEFAULT NULL, -- 위임 신뢰도 (0-100)
    delegated_to         VARCHAR(50)  DEFAULT NULL, -- 위임된 하위 챗봇 ID
    created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conv_session         ON test.conversation_logs(session_id);
CREATE INDEX idx_conv_knox            ON test.conversation_logs(knox_id);
CREATE INDEX idx_conv_chatbot         ON test.conversation_logs(chatbot_id);
CREATE INDEX idx_conv_created         ON test.conversation_logs(created_at DESC);
CREATE INDEX idx_conv_session_created ON test.conversation_logs(session_id, created_at DESC);
```

---

## 2. 도메인 모델 (Python)

> 소스: `backend/core/models.py`

### 2.1 ExecutionRole (Enum)

```python
class ExecutionRole(str, Enum):
    TOOL  = "tool"    # 무상태, 단일 호출 모드
    AGENT = "agent"   # 대화형, 메모리 유지 모드
```

---

### 2.2 RetrievalConfig

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `db_ids` | `list[str]` | `[]` | 검색할 벡터 DB ID 목록 |
| `k` | `int` | `5` | Top-K 검색 결과 수 |
| `filter_metadata` | `dict` | `{}` | 메타데이터 필터 |

---

### 2.3 LLMConfig

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `model` | `str` | 환경변수 | LLM 모델 ID |
| `temperature` | `float` | `0.3` | 샘플링 온도 |
| `max_tokens` | `int` | `1024` | 최대 출력 토큰 |
| `stream` | `bool` | `True` | 스트리밍 여부 |

---

### 2.4 MemoryConfig

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `enabled` | `bool` | `True` | 대화 히스토리 유지 여부 |
| `max_messages` | `int` | `20` | 최대 보관 메시지 수 |

---

### 2.5 SubChatbotRef

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `str` | 하위 챗봇 ID |
| `level` | `int` | 계층 레벨 (1, 2, 3) |
| `default_role` | `ExecutionRole` | 기본 실행 모드 |

---

### 2.6 ChatbotDef (핵심 모델)

챗봇 정의. `chatbots/*.json`에서 로드됩니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `str` | 고유 챗봇 ID |
| `name` | `str` | 표시 이름 |
| `description` | `str` | 설명 |
| `active` | `bool` | 활성 여부 |
| `system_prompt` | `str` | LLM 시스템 프롬프트 |
| `retrieval` | `RetrievalConfig` | RAG 검색 설정 |
| `llm` | `LLMConfig` | LLM 실행 설정 |
| `memory` | `MemoryConfig` | 메모리 설정 |
| `role` | `ExecutionRole` | 기본 실행 역할 |
| `sub_chatbots` | `list[SubChatbotRef]` | 하위 챗봇 목록 |
| `parent_id` | `str \| None` | 상위 챗봇 ID |
| `level` | `int` | 계층 레벨 |
| `policy` | `dict` | 위임 정책 설정 |

**`is_leaf` property**: `sub_chatbots`가 비어 있으면 True  
**`is_root` property**: `parent_id`가 None이면 True

---

### 2.7 Message

| 필드 | 타입 | 설명 |
|------|------|------|
| `role` | `str` | `"user"`, `"assistant"`, `"system"` |
| `content` | `str` | 메시지 내용 |

---

### 2.8 ChatSession

| 필드 | 타입 | 설명 |
|------|------|------|
| `session_id` | `str` | 고유 세션 ID |
| `chatbot_id` | `str` | 연결된 챗봇 ID |
| `user_knox_id` | `str` | 사용자 Knox ID |
| `role_override` | `dict[str, ExecutionRole]` | 챗봇별 역할 오버라이드 |
| `active_level` | `int` | 활성 계층 레벨 |

---

### 2.9 ExecutionContext

런타임에 `factory.py`가 조합하는 실행 컨텍스트.

| 필드 | 타입 | 설명 |
|------|------|------|
| `chatbot_def` | `ChatbotDef` | 챗봇 정의 |
| `session` | `ChatSession` | 현재 세션 |
| `authorized_db_ids` | `list[str]` | 챗봇 범위 ∩ 사용자 권한 |
| `effective_role` | `ExecutionRole` | 실제 실행 역할 (오버라이드 반영) |
| `history` | `list[Message]` | 현재 대화 히스토리 |

---

## 3. 챗봇 JSON 구조

> 소스: `chatbots/*.json`

두 가지 포맷을 지원합니다.

### 3.1 신규 포맷 (capabilities/policy)

```json
{
  "id": "chatbot-hr",
  "name": "인사지원 상위 챗봇",
  "description": "HR 관련 질의를 처리하는 상위 챗봇",
  "active": true,
  "capabilities": {
    "db_ids": ["db_hr_overview"],
    "model": "kimi-k2.5:cloud",
    "system_prompt": "당신은 HR 전문가입니다. 정확하고 친절하게 답변하세요."
  },
  "policy": {
    "temperature": 0.3,
    "max_tokens": 2048,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20,
    "delegation_threshold": 70,
    "enable_parent_delegation": true,
    "multi_sub_execution": true,
    "max_parallel_subs": 2,
    "synthesis_mode": "parallel",
    "hybrid_score_threshold": 0.15
  },
  "sub_chatbots": [
    {"id": "chatbot-hr-policy", "level": 1, "default_role": "agent"},
    {"id": "chatbot-hr-benefit", "level": 1, "default_role": "agent"}
  ],
  "parent_id": "chatbot-company",
  "level": 1
}
```

### 3.2 레거시 포맷 (role/retrieval/llm/memory)

```json
{
  "id": "chatbot-a",
  "name": "기술지원 챗봇",
  "description": "기술 문서 기반 FAQ",
  "active": true,
  "role": "agent",
  "retrieval": {
    "db_ids": ["db_001", "db_002"],
    "k": 5
  },
  "llm": {
    "model": "kimi-k2.5:cloud",
    "temperature": 0.3,
    "max_tokens": 1024,
    "stream": true
  },
  "memory": {
    "enabled": true,
    "max_messages": 20
  },
  "system_prompt": "당신은 기술지원 어시스턴트입니다."
}
```

---

## 4. policy 필드 상세

`policy` 딕셔너리에서 사용 가능한 설정:

| 키 | 타입 | 기본값 | 설명 |
|----|------|--------|------|
| `temperature` | float | 0.3 | LLM 샘플링 온도 |
| `max_tokens` | int | 1024 | 최대 출력 토큰 |
| `stream` | bool | true | SSE 스트리밍 |
| `supported_modes` | list | `["tool","agent"]` | 허용 실행 모드 |
| `default_mode` | string | `"agent"` | 기본 실행 모드 |
| `max_messages` | int | 20 | 메모리 최대 메시지 수 |
| `delegation_threshold` | int | 70 | 위임 결정 신뢰도 임계값 (0-100) |
| `enable_parent_delegation` | bool | false | 상향 위임 허용 여부 |
| `multi_sub_execution` | bool | false | 복수 하위 챗봇 동시 실행 |
| `max_parallel_subs` | int | 2 | 최대 병렬 하위 챗봇 수 |
| `synthesis_mode` | string | `"parallel"` | 응답 합성 방식 |
| `hybrid_score_threshold` | float | 0.15 | 하위 챗봇 선택 최소 스코어 |

---

## 5. 인메모리 데이터 구조

### MemoryManager

```python
# 내부 구조
_data: dict[tuple[str, str], list[Message]]
# 키: (chatbot_id, session_id)
# 값: Message 리스트

# 예시
{
    ("chatbot-hr", "sess-abc"): [
        Message(role="user",      content="연차 신청은?"),
        Message(role="assistant", content="HR 시스템에서..."),
    ],
    ("chatbot-hr", "sess-def"): [...],
    ("chatbot-tech", "sess-abc"): [...],
}
```

### SessionManager

```python
# 내부 구조
_sessions: dict[str, ChatSession]
# 키: session_id

_user_sessions: dict[str, list[str]]
# 키: knox_id → 해당 사용자의 session_id 목록
```

---

## 6. ConversationLog (대화 로그 모델)

```python
@dataclass
class ConversationLog:
    session_id: str
    knox_id: str
    chatbot_id: str
    user_message: str
    assistant_response: str
    tokens_used: int = 0
    latency_ms: int = 0
    search_results_count: int = 0
    confidence_score: float | None = None
    delegated_to: str | None = None   # 위임된 챗봇 ID
    created_at: datetime = field(default_factory=datetime.utcnow)
```

---

## 7. 관계도 요약

```
Knox ID (사용자)
  │
  ├─ N:M ─ ChatbotDef (user_chatbot_access)
  │           │
  │           ├─ 1:N ─ ChatSession
  │           │           │
  │           │           └─ 1:N ─ Message (MemoryManager)
  │           │
  │           ├─ 0:N ─ SubChatbotRef → ChatbotDef (계층)
  │           │
  │           └─ RetrievalConfig.db_ids → Ingestion Server
  │
  └─ 1:N ─ ConversationLog
```
