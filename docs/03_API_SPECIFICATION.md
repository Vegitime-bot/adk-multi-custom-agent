# 03. API 명세 (API Specification)

## Base URL

```
http://localhost:8080
```

---

## 인증

| 모드 | 방식 |
|------|------|
| `USE_MOCK_AUTH=true` | 인증 없음, `knox_id = "user-001"` 고정 |
| `USE_MOCK_AUTH=false` | SSO 세션 쿠키 필요 (`/sso` 로그인 먼저) |

---

## 1. 챗봇 대화 API

### POST /api/chat

챗봇과 대화합니다. SSE(Server-Sent Events) 스트리밍으로 응답합니다.

**Request**

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "chatbot_id": "chatbot-hr",
  "message": "연차 신청은 어떻게 하나요?",
  "session_id": "sess-abc123",
  "mode": "agent",
  "role_override": {
    "chatbot-hr-policy": "tool"
  },
  "active_level": 1
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `chatbot_id` | string | Y | 챗봇 ID |
| `message` | string | Y | 사용자 메시지 |
| `session_id` | string | N | 세션 ID (미제공 시 자동 생성) |
| `mode` | string | N | `"tool"` 또는 `"agent"` (기본값 덮어쓰기) |
| `role_override` | object | N | 특정 챗봇 ID별 실행 모드 오버라이드 |
| `active_level` | integer | N | 활성 계층 레벨 (기본: 1) |

**Response (SSE Stream)**

```
Content-Type: text/event-stream

data: 연차

data:  신청은

data:  HR

data:  시스템에서

data:  가능합니다.

data: [DONE]
```

각 `data:` 라인은 LLM 출력의 토큰 청크입니다.

**Error Responses**

| 상태코드 | 사유 | 응답 본문 |
|---------|------|----------|
| 404 | 챗봇 없음 또는 비활성 | `{"detail": "Chatbot not found or inactive"}` |
| 403 | 접근 권한 없음 | `{"detail": "Access denied"}` |
| 400 | 지원하지 않는 모드 | `{"detail": "Mode 'X' not supported by this chatbot"}` |

---

## 2. 세션 API

### POST /api/sessions

새 세션을 생성합니다.

**Request**

```json
{
  "chatbot_id": "chatbot-hr",
  "role_override": {},
  "active_level": 1
}
```

**Response**

```json
{
  "session_id": "sess-7f3a2b1c",
  "chatbot_id": "chatbot-hr",
  "knox_id": "user-001",
  "created_at": "2026-04-07T10:00:00Z"
}
```

---

### GET /api/sessions/{session_id}/history

세션의 대화 히스토리를 조회합니다.

**Path Parameters**

| 파라미터 | 설명 |
|---------|------|
| `session_id` | 세션 ID |

**Response**

```json
{
  "session_id": "sess-7f3a2b1c",
  "chatbot_id": "chatbot-hr",
  "history": [
    {"role": "user", "content": "연차 신청은 어떻게 하나요?"},
    {"role": "assistant", "content": "연차 신청은 HR 시스템에서 가능합니다..."}
  ]
}
```

---

## 3. 관리자 API

> 관리자 패널: `GET /admin` → HTML 페이지

### GET /admin/api/chatbots

모든 챗봇 목록을 반환합니다.

**Response**

```json
[
  {
    "id": "chatbot-hr",
    "name": "인사지원 상위 챗봇",
    "description": "HR 관련 질의 처리",
    "active": true,
    "role": "agent",
    "sub_chatbots": ["chatbot-hr-policy", "chatbot-hr-benefit"],
    "parent_id": "chatbot-company",
    "level": 1,
    "db_ids": ["db_hr_overview"]
  }
]
```

---

### POST /admin/api/chatbots

새 챗봇을 생성합니다. `chatbots/{id}.json` 파일로 저장됩니다.

**Request**

```json
{
  "id": "chatbot-new",
  "name": "신규 챗봇",
  "description": "설명",
  "active": true,
  "capabilities": {
    "db_ids": ["db_001"],
    "model": "GLM4.7",
    "system_prompt": "당신은 도움이 되는 어시스턴트입니다."
  },
  "policy": {
    "temperature": 0.3,
    "max_tokens": 1024,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20
  }
}
```

**Response**

```json
{
  "message": "Chatbot created successfully",
  "chatbot_id": "chatbot-new"
}
```

---

### PUT /admin/api/chatbots/{chatbot_id}

챗봇을 수정합니다.

**Request**: POST와 동일한 스키마

**Response**

```json
{
  "message": "Chatbot updated successfully"
}
```

---

### DELETE /admin/api/chatbots/{chatbot_id}

챗봇을 삭제합니다. (`chatbots/{id}.json` 파일 삭제)

**Response**

```json
{
  "message": "Chatbot deleted successfully"
}
```

---

### POST /admin/api/chatbots/reload

디스크에서 챗봇 정의를 다시 로드합니다.

**Response**

```json
{
  "message": "Chatbots reloaded",
  "count": 12
}
```

---

## 4. 권한 API

### GET /api/permissions/users/{knox_id}

사용자의 챗봇 접근 권한 목록을 반환합니다.

**Response**

```json
[
  {
    "id": 1,
    "knox_id": "user-001",
    "chatbot_id": "chatbot-hr",
    "can_access": true,
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### GET /api/permissions/check/{chatbot_id}

현재 사용자의 특정 챗봇 접근 권한을 확인합니다.

**Response**

```json
{
  "knox_id": "user-001",
  "chatbot_id": "chatbot-hr",
  "can_access": true
}
```

---

### POST /api/permissions/

접근 권한을 부여합니다.

**Request**

```json
{
  "knox_id": "user-002",
  "chatbot_id": "chatbot-tech",
  "can_access": true
}
```

**Response**

```json
{
  "message": "Permission granted",
  "id": 42
}
```

---

### PUT /api/permissions/{permission_id}

권한을 수정합니다.

**Request**

```json
{
  "can_access": false
}
```

---

### DELETE /api/permissions/{permission_id}

권한을 삭제합니다.

---

### GET /api/permissions/chatbots/{chatbot_id}/users

특정 챗봇에 접근 가능한 사용자 목록을 반환합니다.

**Response**

```json
[
  {"knox_id": "user-001", "can_access": true},
  {"knox_id": "user-002", "can_access": true}
]
```

---

## 5. 대화 기록 API

### GET /api/conversations/session/{session_id}

세션별 대화 기록을 반환합니다.

**Response**

```json
[
  {
    "id": 1,
    "session_id": "sess-001",
    "knox_id": "user-001",
    "chatbot_id": "chatbot-hr",
    "user_message": "연차 신청은 어떻게 하나요?",
    "assistant_response": "연차 신청은 HR 시스템에서 가능합니다...",
    "tokens_used": 245,
    "latency_ms": 1200,
    "confidence_score": 85.5,
    "delegated_to": null,
    "created_at": "2026-04-07T10:00:00Z"
  }
]
```

---

### GET /api/conversations/user/{knox_id}

사용자별 대화 기록을 반환합니다.

---

### GET /api/conversations/chatbot/{chatbot_id}

챗봇별 대화 기록을 반환합니다.

---

### GET /api/conversations/stats

대화 통계를 반환합니다.

**Response**

```json
{
  "total_conversations": 1250,
  "total_sessions": 320,
  "avg_confidence_score": 78.3,
  "top_chatbots": [
    {"chatbot_id": "chatbot-hr", "count": 450},
    {"chatbot_id": "chatbot-tech", "count": 380}
  ],
  "delegation_rate": 0.23
}
```

---

### GET /api/conversations/recent

최근 대화 기록을 반환합니다.

**Query Parameters**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `limit` | 20 | 반환할 최대 개수 |

---

## 6. SSO API (USE_MOCK_AUTH=false 시 활성)

### GET /sso

SSO 로그인을 시작합니다. OIDC Authorization Code Flow 시작.

**Response**: SSO 서버로 302 리다이렉트

---

### GET /auth/acs

SSO 콜백 엔드포인트. 인증 코드를 받아 토큰 교환 후 세션 설정.

**Query Parameters**

| 파라미터 | 설명 |
|---------|------|
| `code` | Authorization code |
| `state` | CSRF 방지용 state 값 |

**Response**: 챗봇 UI로 302 리다이렉트

---

### POST /auth/logout

SSO 로그아웃 및 세션 삭제.

**Response**: SSO 로그아웃 URL로 302 리다이렉트

---

## 7. 헬스체크

### GET /health

서버 상태를 확인합니다.

**Response**

```json
{
  "status": "ok",
  "use_mock_db": true,
  "use_mock_auth": true,
  "ingestion_url": "http://localhost:8001",
  "llm_base_url": "http://localhost:11434/v1"
}
```

---

## 8. Ingestion 서버 API (외부, 참고)

> 출처: `INGESTION_API.md`

### POST /search

벡터 검색을 수행합니다. (Multi Custom Agent에서 내부적으로 호출)

**Request**

```json
{
  "query": "연차 신청 방법",
  "index_names": ["db_hr_overview", "db_hr_policy"],
  "top_k": 5,
  "threshold": 0.0,
  "filter_metadata": {}
}
```

**Header**

```
x-api-key: {INGESTION_API_KEY}
```

**Response**

```json
{
  "results": [
    {
      "content": "연차는 HR 시스템에서 신청 가능합니다...",
      "metadata": {"source": "hr_manual.pdf", "page": 12},
      "score": 0.92
    }
  ]
}
```

---

## 에러 코드 요약

| 상태코드 | 의미 |
|---------|------|
| 200 | 성공 |
| 400 | 잘못된 요청 (파라미터 오류, 지원하지 않는 모드 등) |
| 401 | 인증 필요 (SSO 로그인 필요) |
| 403 | 권한 없음 (챗봇 접근 불가) |
| 404 | 챗봇/세션/권한 없음 |
| 500 | 서버 내부 오류 |

---

## Swagger UI

서버 실행 후 다음 URL에서 인터랙티브 API 문서 확인 가능:

```
http://localhost:8080/docs
```
