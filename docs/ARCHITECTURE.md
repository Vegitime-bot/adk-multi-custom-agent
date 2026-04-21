# ARCHITECTURE.md - Multi Custom Agent Service

---

## Authorization

### Authentication & Authorization
- 인증은 사내 SSO를 통해 사용자 식별을 수행한다. (상세 프로토콜 TBD)
- 권한 판단은 PostgreSQL을 정책 저장소(Source of Truth)로 사용한다.
- 권한 검사는 실행 컨텍스트 생성 이전 또는 최소한 검색 이전에 수행되어야 한다.

> Authentication identifies the user via SSO, Authorization determines permissions via PostgreSQL.

### Chatbot Access Control
- 사용자는 허용된 챗봇에만 접근 가능해야 한다.
- 챗봇 접근 권한은 PostgreSQL에서 관리된다.
- 권한 없는 챗봇은 실행 요청에서 차단되어야 하며, UI/API에서도 노출되지 않는 것이 바람직하다.
- 명시적 deny는 allow보다 우선한다.

> Chatbot access must be validated before runtime execution.

### Data Scope Authorization
- 검색 가능한 데이터 범위는 보안 경계로 취급한다.
- 최종 검색 범위: `final_scope = chatbot_scope ∩ user_scope`
- ingestion 서버로 전달되는 `db_ids`는 사용자 입력이 아니라, 권한 검사를 통과한 결과로만 생성되어야 한다.

> Retrieval scope is a security boundary, not just configuration.

### PostgreSQL 역할
PostgreSQL은 다음 권한 정보를 관리한다:
- 사용자 식별 매핑 (SSO 연결)
- 챗봇 접근 권한
- 실행 역할 권한 (Tool / Agent)
- 데이터 소스 접근 범위
- 관리자 권한

> PostgreSQL acts as the system of record for all authorization decisions.

### Audit Logging
- 모든 접근 이벤트(챗봇 실행, 데이터 검색, 권한 거부)는 기록한다.
- 세부 보존 정책은 추후 정의한다.

> All authorization-related events must be logged. Retention policy is TBD.

### Agent Permission Delegation
- Agent가 다른 Agent 또는 Tool을 호출할 때, 기본적으로 원래 사용자의 권한을 상속한다.
- 특정 케이스에서는 권한 범위를 별도로 구성할 수 있어야 한다.

> Agent execution inherits the originating user's permissions by default. Delegation scope is configurable.

---

> **전체 요약:**
> SSO identifies the user, PostgreSQL defines what the user can access, and all chatbot execution and retrieval must be constrained by these policies.

---

## UI 전략

### 초기 버전: HTML 기반
- 빠른 프로토타이핑 및 기능 검증 목적
- 백엔드(FastAPI)와 API로만 통신 — UI가 직접 DB나 비즈니스 로직을 건드리지 않음

### 이후 버전: React 전환
- 기능이 안정화된 이후 React로 마이그레이션
- API가 명확히 분리되어 있으므로 백엔드 변경 없이 프론트만 교체 가능

> UI는 항상 FastAPI 엔드포인트를 통해서만 데이터에 접근한다. 이 원칙을 지키면 HTML → React 전환 비용이 최소화된다.

---

## 기술 스택

| 항목 | 선택 |
|------|------|
| Language | Python |
| Web Framework | FastAPI |
| HTTP Client | requests |
| Database (권한) | PostgreSQL |
| 인증 | 사내 SSO (상세 TBD) |
| UI (초기) | HTML |
| UI (추후) | React |
| Test Framework | pytest |

---

_마지막 업데이트: 2026-03-26_
