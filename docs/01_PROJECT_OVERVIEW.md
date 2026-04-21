# 01. 프로젝트 개요 (Project Overview)

## 목적

**Multi Custom Agent Service**는 기업 내부에서 사용하는 멀티 테넌트 RAG(Retrieval-Augmented Generation) 챗봇 플랫폼입니다.

- 여러 독립적인 챗봇을 하나의 서버에서 운영
- 각 챗봇은 고유한 벡터 DB 범위, 시스템 프롬프트, 권한, 실행 모드를 가짐
- 3단계 계층적 위임(Hierarchical Delegation): 신뢰도가 낮은 질의를 전문 하위 챗봇에 위임
- SSO 기반 사용자 인증 및 챗봇별 접근 제어

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 멀티 테넌트 챗봇 | JSON 파일로 챗봇 정의, 코드 수정 없이 추가/수정 가능 |
| RAG 검색 | 외부 Ingestion 서버와 연동하여 문서 기반 답변 생성 |
| 계층적 위임 | Parent → Child → Grandchild 3단계 위임, 신뢰도 기반 상향 위임 |
| 실행 모드 | Tool(무상태) / Agent(대화형) 선택 가능 |
| 스트리밍 응답 | SSE(Server-Sent Events)로 실시간 LLM 출력 |
| 접근 제어 | Knox ID 기반 사용자-챗봇 권한 관리 |
| 대화 기록 | 세션별 대화 히스토리 저장/조회 |
| 관리자 패널 | 웹 기반 챗봇 CRUD, 계층 뷰, 권한 관리, 통계 |
| SSO 연동 | OIDC/OAuth2 기반 사내 SSO (선택적) |

---

## 사용자 흐름

### 1. 일반 사용자 (챗봇 대화)

```
[사용자]
  │
  ├─ 브라우저 접속 → http://localhost:8080
  │     (USE_MOCK_AUTH=true: 챗봇 UI 바로 표시)
  │     (USE_MOCK_AUTH=false: SSO 로그인 → 리다이렉트 → 챗봇 UI)
  │
  ├─ 챗봇 선택 (본인에게 권한 있는 챗봇만 표시)
  │
  ├─ 메시지 입력 → POST /api/chat
  │     → 권한 확인
  │     → 세션 생성/조회
  │     → RAG 검색 (Ingestion 서버)
  │     → 신뢰도 계산 → 위임 판단
  │     → LLM 호출 → SSE 스트리밍 응답
  │
  └─ 대화 히스토리 유지 (Agent 모드)
```

### 2. 관리자 (챗봇 관리)

```
[관리자]
  │
  ├─ 브라우저 접속 → http://localhost:8080/admin
  │
  ├─ 챗봇 목록 조회 → GET /admin/api/chatbots
  │
  ├─ 챗봇 생성/수정 → POST/PUT /admin/api/chatbots
  │     (chatbots/*.json 파일로 저장)
  │
  ├─ 권한 관리 → GET/POST/DELETE /api/permissions
  │
  └─ 통계 조회 → GET /api/conversations/stats
```

### 3. 계층적 위임 흐름

```
[사용자 질의]
  │
  ├─ 상위 챗봇 (Level 1: chatbot-hr)
  │     └─ 신뢰도 ≥ 임계값(70)? → 직접 답변
  │     └─ 신뢰도 < 임계값? → 하위 챗봇 선택 (하이브리드 스코어링)
  │           ├─ chatbot-hr-policy (인사 정책 전문)
  │           └─ chatbot-hr-benefit (복리후생 전문)
  │                 └─ 병렬 실행 (max_parallel_subs: 2)
  │                 └─ 응답 합성 → 최종 답변
  │
  └─ enable_parent_delegation=true 시:
        하위에서도 신뢰도 낮으면 상위로 다시 위임(상향 위임)
```

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 프레임워크 | FastAPI 0.115.6 |
| 데이터 검증 | Pydantic 2.10.3 |
| ASGI 서버 | Uvicorn 0.32.1 |
| LLM 클라이언트 | OpenAI SDK 1.59.3 (OpenAI 호환 엔드포인트) |
| 데이터베이스 | PostgreSQL (SQLAlchemy 2.0.36) / 인메모리 Mock |
| DB 드라이버 | psycopg2-binary 2.9.10 |
| HTTP 클라이언트 | httpx 0.28.1, requests 2.32.3 |
| 인증 | OIDC/OAuth2 SSO 또는 Mock |
| JWT | python-jose 3.3.0 |
| 세션 | itsdangerous 2.2.0 |
| 테스트 | pytest 8.3.4 + pytest-asyncio 0.24.0 |
| 프론트엔드 | 정적 HTML/CSS/JS (React 빌드 아티팩트) |

---

## 배포 요구사항

- **Python:** 3.9 이상
- **외부 서비스:**
  - Ingestion 서버 (벡터 검색, 별도 운영): `http://{host}:8001`
  - LLM 서버 (OpenAI 호환 API): `http://{host}:{port}/v1`
  - PostgreSQL (선택, USE_MOCK_DB=false 시): 5432
  - SSO 서버 (선택, USE_MOCK_AUTH=false 시)

---

## 프로젝트 구조 요약

```
multi-custom-agent/
├── app.py                    # FastAPI 앱 진입점
├── config.py                 # 전역 설정 (환경변수)
├── requirements.txt          # Python 의존성
├── .env / .env.example       # 환경변수 템플릿
│
├── backend/                  # 백엔드 핵심 로직
│   ├── api/                  # REST API 라우터
│   ├── core/                 # 도메인 모델 & 팩토리
│   ├── managers/             # 리소스 수명주기 관리
│   ├── executors/            # 실행 엔진 (Tool/Agent/Hierarchical)
│   ├── roles/                # 역할 기반 실행 디스패치
│   ├── retrieval/            # RAG 검색 클라이언트
│   ├── llm/                  # LLM API 클라이언트
│   ├── permissions/          # 접근 제어
│   ├── conversation/         # 대화 기록
│   ├── database/             # DB 연결
│   └── auth/                 # 인증
│
├── chatbots/                 # 챗봇 정의 JSON 파일들
├── database/                 # DB 스키마 SQL
├── static/                   # 웹 UI (HTML/CSS/JS)
├── tests/                    # 통합 테스트
└── docs/                     # 문서
```
