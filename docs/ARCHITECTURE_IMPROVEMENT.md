# Multi Custom Agent Service - 아키텍처 개선 제안서

## 📋 개요

**작성일:** 2026-03-31  
**주제:** Tool/Agent 역할 분리 및 Executor 기반 아키텍처 개선

---

## 🔥 현재 문제점 (AS-IS)

### 1. 역할이 설정값에 불과함
```json
// 현재 구조 - chatbot.json
{
  "id": "sales-bot",
  "role": "tool"  // ← 단순 라벨
}
```

- `role`이 config에 있어 "라벨"에 불과
- 실행 로직이 Tool/Agent 간 동일
- 하나의 챗봇을 다양한 방식으로 사용 불가

### 2. 재사용성 저하
- 동일한 DB/모델을 쓰는 챗봇도 role만 다르면 중복 정의 필요
- "챗봇"과 "실행 방식"이 결합되어 있음

### 3. ADK/오케스트레이터 연동 어려움
```
상위 Agent → 하위 Tool 호출
         ↓
현재는 role이 고정되어 자연스러운 호출 구조 불가
```

---

## ✅ 개선 방향 (TO-BE)

### 핵심 원칙
> **챗봇 정의는 "능력"만 가진다  
> Tool/Agent는 "실행 방식"이다  
> 같은 챗봇을 Tool은 함수처럼, Agent는 대화 주체처럼 실행한다**

---

## 🏗️ 새로운 아키텍처

### 1. 챗봇 정의 (능력 중심)

```json
// chatbot.json - 능력만 정의
{
  "id": "sales-bot",
  "name": "영업 지원 챗봇",
  "description": "영업 관련 문서 검색 및 응답",
  
  "capabilities": {
    "db_ids": ["db_001", "db_002"],
    "model": "kimi-k2.5:cloud",
    "system_prompt": "당신은 영업 지원 전문가입니다..."
  },
  
  "policy": {
    "max_tokens": 1024,
    "temperature": 0.3,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent"
  }
}
```

**변경사항:**
- ❌ `role` 필드 제거
- ✅ `capabilities` - 검색 가능한 DB, 모델, 프롬프트
- ✅ `policy` - 실행 정책, 지원 모드, 기본값

---

### 2. Executor 분리 (실행 계층)

```
backend/
├── executors/
│   ├── __init__.py
│   ├── base_executor.py      # 공통 기능
│   ├── tool_executor.py      # Tool 모드 실행
│   └── agent_executor.py     # Agent 모드 실행
```

#### BaseExecutor (공통)
```python
class BaseExecutor(ABC):
    """공통 실행 기능"""
    
    def __init__(self, chatbot_def: ChatbotDef, ingestion_client: IngestionClient):
        self.chatbot_def = chatbot_def
        self.ingestion = ingestion_client
    
    def _retrieve(self, query: str, db_ids: list[str]) -> str:
        """RAG 검색 - 공통"""
        results = self.ingestion.search(db_ids=db_ids, query=query)
        return format_context(results)
    
    def _build_messages(self, system: str, user: str, context: str) -> list[dict]:
        """메시지 구성 - 공통"""
        ...
    
    @abstractmethod
    def execute(self, message: str, session_id: str | None = None) -> Generator[str, None, None]:
        """실행 - 하위 클래스 구현"""
        pass
```

#### ToolExecutor (함수처럼)
```python
class ToolExecutor(BaseExecutor):
    """Tool 모드: 상태 비저장, 단발성 호출"""
    
    def execute(self, message: str, session_id: str | None = None) -> Generator[str, None, None]:
        # 1. 검색 (메모리 없음)
        context = self._retrieve(message, self.chatbot_def.capabilities.db_ids)
        
        # 2. LLM 호출 (히스토리 없음)
        messages = self._build_messages(
            system=self.chatbot_def.capabilities.system_prompt,
            user=message,
            context=context
        )
        
        # 3. 스트리밍 응답
        yield from self._stream_chat(messages)
```

#### AgentExecutor (대화 주체처럼)
```python
class AgentExecutor(BaseExecutor):
    """Agent 모드: 메모리 유지, 대화형"""
    
    def __init__(self, chatbot_def: ChatbotDef, ingestion_client: IngestionClient, 
                 memory_manager: MemoryManager):
        super().__init__(chatbot_def, ingestion_client)
        self.memory = memory_manager
    
    def execute(self, message: str, session_id: str) -> Generator[str, None, None]:
        # 1. 메모리에서 히스토리 복원
        history = self.memory.get_history(self.chatbot_def.id, session_id)
        
        # 2. 검색
        context = self._retrieve(message, self.chatbot_def.capabilities.db_ids)
        
        # 3. 메시지 구성 (히스토리 포함)
        messages = self._build_messages_with_history(
            system=self.chatbot_def.capabilities.system_prompt,
            history=history,
            user=message,
            context=context
        )
        
        # 4. 스트리밍 + 메모리 저장
        full_response = []
        for chunk in self._stream_chat(messages):
            full_response.append(chunk)
            yield chunk
        
        # 5. 메모리 저장
        self.memory.append_pair(
            self.chatbot_def.id, session_id,
            user_content=message,
            assistant_content="".join(full_response)
        )
```

---

### 3. API 엔드포인트 변경

#### 옵션 A: 경로 기반 분리 (권장)
```python
# Tool 모드 (함수처럼)
POST /tools/{chatbot_id}
Body: {
  "message": "...",
  "context": {}  # 선택적 컨텍스트
}

# Agent 모드 (대화형)
POST /agents/{chatbot_id}
Body: {
  "message": "...",
  "session_id": "..."  # 필수
}

# 기존 호환 (default_mode 사용)
POST /chat/{chatbot_id}
Body: {
  "message": "...",
  "session_id": "...",
  "mode": "tool" | "agent"  # 선택적, 없으면 default_mode
}
```

#### 옵션 B: 쿼리 파라미터
```python
POST /chat/{chatbot_id}?mode=tool
POST /chat/{chatbot_id}?mode=agent
```

---

### 4. 권한 모델 변경

```python
# 사용자별 모드 사용 가능 여부
class UserPermissions:
    def __init__(self):
        self.chatbot_access = {
            "sales-bot": {
                "access": True,
                "allowed_modes": ["tool", "agent"],  # 둘 다 가능
                "default_mode": "agent"
            },
            "hr-bot": {
                "access": True,
                "allowed_modes": ["tool"],  # Tool만 가능
                "default_mode": "tool"
            }
        }
```

**권한 체크 흐름:**
```
1. 사용자가 chatbot_id로 요청
2. 사용자의 chatbot 접근 권한 확인
3. 요청 mode가 allowed_modes에 있는지 확인
4. 허용되면 해당 mode로 실행
5. 미지정 시 default_mode 사용
```

---

### 5. 실행 흐름 비교

#### Tool 모드
```
요청 → ToolExecutor
  → RAG 검색 (DB 스코프 적용)
  → LLM 호출 (히스토리 없음)
  → 응답 반환
  → (메모리 저장 없음)
```

#### Agent 모드
```
요청 → AgentExecutor
  → 세션 확인/생성
  → 메모리에서 히스토리 복원
  → RAG 검색 (DB 스코프 적용)
  → LLM 호출 (히스토리 포함)
  → 응답 스트리밍
  → 메모리 저장
```

---

## 📊 변경사항 요약

| 항목 | AS-IS | TO-BE |
|------|-------|-------|
| **챗봇 정의** | role 포함 | 능력만 정의 |
| **역할 구분** | 설정값 | 실행 방식 |
| **Executor** | 단일 | Tool/Agent 분리 |
| **메모리** | role에 따라 다름 | mode에 따라 다름 |
| **재사용성** | 낮음 (중복 정의) | 높음 (동일 챗봗, 다른 모드) |
| **API** | `/api/chat` | `/tools/`, `/agents/`, `/chat/` |
| **권한** | 챗봗 단위 | 챗봗 + mode 단위 |

---

## 🔄 마이그레이션 계획

### Phase 1: Executor 구현 (2-3시간)
- [ ] `executors/` 디렉토리 생성
- [ ] `BaseExecutor` 구현
- [ ] `ToolExecutor` 구현
- [ ] `AgentExecutor` 구현

### Phase 2: API 변경 (1시간)
- [ ] 새 엔드포인트 추가 (`/tools/`, `/agents/`)
- [ ] 기존 `/chat/` 유지 (하위호환)

### Phase 3: 설정 마이그레이션 (30분)
- [ ] 기존 `chatbot_*.json` 변환
- [ ] `role` → `policy.supported_modes`

### Phase 4: 권한 모듈 업데이트 (2시간)
- [ ] `allowed_modes` 필드 추가
- [ ] 권한 체크 로직 변경

---

## 💡 핵심 인사이트

### 같은 챗봇, 다른 사용법
```python
# sales-bot을 다양하게 사용

# 1. Tool로 사용 (시스템 내부 호출)
ToolExecutor(sales_bot).execute("Q3 매출 현황")
→ 즉시 응답, 메모리 없음

# 2. Agent로 사용 (사용자 대화)
AgentExecutor(sales_bot).execute("Q3 매출 현황 알려줘", session_id="user-123")
→ 대화 맥락 유지, 메모리 저장

# 3. 사용자는 접근 권한에 따라 선택
user.permissions = {
    "sales-bot": ["tool"]  # Tool만 가능
}
→ Agent 모드 요청 시 권한 거부
```

---

## ❓ 결정 필요사항

| 항목 | 선택지 | 권장 |
|------|--------|------|
| API 설계 | A. 경로 기반 / B. 쿼리 파라미터 | **A** |
| 마이그레이션 타이밍 | 즉시 / 점진적 / 보류 | **점진적** |
| 하위호환 | 유지 / 중단 | **유지** |

---

## 📝 한 줄 요약

> **챗봇은 "능력"만 정의하고, Tool은 함수처럼, Agent는 대화 주체처럼 실행하자.**
