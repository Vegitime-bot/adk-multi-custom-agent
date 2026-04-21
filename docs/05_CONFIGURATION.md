# 05. 설정 및 배포 가이드 (Configuration & Deployment)

## 1. 환경변수 전체 목록

> 소스: `config.py`, `.env.example`

### 1.1 모드 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `USE_MOCK_DB` | `true` | `true`: 인메모리 Mock DB / `false`: PostgreSQL |
| `USE_MOCK_AUTH` | `true` | `true`: 인증 없이 knox_id="user-001" / `false`: SSO |

---

### 1.2 서버 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 서버 바인드 주소 |
| `PORT` | `8080` | 서버 포트 |
| `DEBUG` | `false` | `true` 시 파일 변경 감지 자동 재시작 |

---

### 1.3 LLM 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI 호환 LLM 엔드포인트 |
| `LLM_API_KEY` | `dummy-key` | LLM API 인증 키 |
| `LLM_DEFAULT_MODEL` | `GLM4.7` | 기본 LLM 모델 ID |
| `LLM_TIMEOUT` | `120` | LLM 요청 타임아웃 (초) |
| `LLM_DEFAULT_TEMPERATURE` | `0.3` | 기본 온도값 |
| `LLM_DEFAULT_MAX_TOKENS` | `1024` | 기본 최대 토큰 수 |

---

### 1.4 Ingestion 서버 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `INGESTION_BASE_URL` | `http://localhost:8001` | 벡터 검색 서버 URL |
| `INGESTION_API_KEY` | `secret-key` | Ingestion 서버 인증 키 (헤더: `x-api-key`) |

---

### 1.5 PostgreSQL 설정 (USE_MOCK_DB=false 시 필요)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PG_HOST` | `localhost` | PostgreSQL 호스트 |
| `PG_PORT` | `5432` | PostgreSQL 포트 |
| `PG_DB` | `chatbot_db` | 데이터베이스 이름 |
| `PG_USER` | `postgres` | 사용자 이름 |
| `PG_PASSWORD` | `password` | 비밀번호 |

`DATABASE_URL`은 위 값으로 자동 조합:  
`postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}`

---

### 1.6 보안 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SECRET_KEY` | 필수 | 세션 서명 키 (32바이트 이상 권장) |
| `SSL_VERIFY` | `false` | SSL 인증서 검증 여부 (내부망 false) |

---

### 1.7 SSO 설정 (USE_MOCK_AUTH=false 시 필요)

| 변수 | 설명 |
|------|------|
| `SSO_ISSUER` | SSO 서버 발급자 URL |
| `SSO_CLIENT_ID` | OAuth2 클라이언트 ID |
| `SSO_CLIENT_SECRET` | OAuth2 클라이언트 시크릿 |
| `SSO_REDIRECT_URI` | 콜백 URI (`/auth/acs`) |
| `SSO_AUTH_URL` | Authorization 엔드포인트 |
| `SSO_TOKEN_URL` | Token 엔드포인트 |
| `SSO_USERINFO_URL` | Userinfo 엔드포인트 |
| `SSO_LOGOUT_URL` | Logout 엔드포인트 |
| `SSO_SCOPES` | OIDC 스코프 (기본: `openid email profile`) |

---

## 2. .env 파일 예시

```bash
# ============================================
# 모드 설정
# ============================================
USE_MOCK_DB=true
USE_MOCK_AUTH=true

# ============================================
# 서버 설정
# ============================================
HOST=0.0.0.0
PORT=8080
DEBUG=false

# ============================================
# 보안
# ============================================
SECRET_KEY=change-this-in-production-use-openssl-rand-base64-32

# ============================================
# LLM 설정 (OpenAI 호환 API)
# ============================================
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=dummy-key
LLM_DEFAULT_MODEL=GLM4.7
LLM_TIMEOUT=120
LLM_DEFAULT_TEMPERATURE=0.3
LLM_DEFAULT_MAX_TOKENS=1024

# ============================================
# Ingestion 서버 (벡터 검색)
# ============================================
INGESTION_BASE_URL=http://localhost:8001
INGESTION_API_KEY=secret-key

# ============================================
# SSL
# ============================================
SSL_VERIFY=false

# ============================================
# PostgreSQL (USE_MOCK_DB=false 시 필요)
# ============================================
# PG_HOST=localhost
# PG_PORT=5432
# PG_DB=chatbot_db
# PG_USER=postgres
# PG_PASSWORD=password

# ============================================
# SSO (USE_MOCK_AUTH=false 시 필요)
# ============================================
# SSO_ISSUER=https://sso.company.com
# SSO_CLIENT_ID=your-client-id
# SSO_CLIENT_SECRET=your-client-secret
# SSO_REDIRECT_URI=http://localhost:8080/auth/acs
# SSO_AUTH_URL=https://sso.company.com/oauth/authorize
# SSO_TOKEN_URL=https://sso.company.com/oauth/token
# SSO_USERINFO_URL=https://sso.company.com/oauth/userinfo
# SSO_LOGOUT_URL=https://sso.company.com/oauth/logout
# SSO_SCOPES=openid email profile
```

---

## 3. 로컬 개발 환경 설정

### 3.1 사전 요구사항

- Python 3.9 이상
- pip
- (선택) PostgreSQL 15+

### 3.2 설치 및 실행

```bash
# 1. 저장소 클론
git clone <repo-url>
cd multi-custom-agent

# 2. 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 필요한 값 설정

# 5. Mock Ingestion 서버 실행 (터미널 1)
python mock_ingestion_server.py

# 6. 메인 서버 실행 (터미널 2)
python app.py

# 또는 uvicorn 직접 실행
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### 3.3 접속 URL

| URL | 설명 |
|-----|------|
| `http://localhost:8080` | 챗봇 UI (Mock Auth 시 바로 접속) |
| `http://localhost:8080/admin` | 관리자 패널 |
| `http://localhost:8080/docs` | Swagger UI (API 문서) |
| `http://localhost:8080/health` | 헬스체크 |

---

## 4. PostgreSQL 연동 (프로덕션)

```bash
# 1. 환경변수 설정
USE_MOCK_DB=false
PG_HOST=your-db-host
PG_PORT=5432
PG_DB=chatbot_db
PG_USER=chatbot_user
PG_PASSWORD=secure_password

# 2. 스키마 생성 (최초 1회)
psql -U chatbot_user -d chatbot_db -f database/schema.sql
psql -U chatbot_user -d chatbot_db -f database/schema_conversation.sql
```

> 주의: `updated_at` 컬럼은 `schema.sql`에 정의되어 있으나 ORM 모델에서 제거됨 (커밋 `ede75cc`)

SQLAlchemy가 서버 시작 시 테이블을 자동 생성합니다 (`init_tables()`).

---

## 5. SSO 연동 (프로덕션)

상세 가이드: [docs/SSO_INTEGRATION.md](SSO_INTEGRATION.md)

```bash
USE_MOCK_AUTH=false
SSO_ISSUER=https://sso.company.com
SSO_CLIENT_ID=multi-chatbot-client
SSO_CLIENT_SECRET=<secret>
SSO_REDIRECT_URI=https://chatbot.company.com/auth/acs
SECRET_KEY=$(openssl rand -base64 32)
```

**사용자 흐름:**
1. 브라우저 → `GET /` → 세션 없으면 `GET /sso`로 리다이렉트
2. SSO 서버 → 로그인 → `GET /auth/acs?code=...` 콜백
3. 서버 → 토큰 교환 → `knox_id` 추출 → 세션 설정
4. `GET /` → 챗봇 UI 표시

---

## 6. 챗봇 추가/수정

챗봇은 JSON 파일로 관리됩니다. 코드 수정 없이 챗봇을 추가할 수 있습니다.

```bash
# 1. 새 챗봇 정의 파일 생성
cat > chatbots/chatbot-new.json << 'EOF'
{
  "id": "chatbot-new",
  "name": "신규 챗봇",
  "description": "설명",
  "active": true,
  "capabilities": {
    "db_ids": ["db_new"],
    "model": "GLM4.7",
    "system_prompt": "당신은 전문 어시스턴트입니다."
  },
  "policy": {
    "default_mode": "agent",
    "temperature": 0.3,
    "max_tokens": 1024
  }
}
EOF

# 2. 서버에 리로드 요청
curl -X POST http://localhost:8080/admin/api/chatbots/reload
```

---

## 7. 설정 우선순위

챗봇의 LLM 설정은 다음 우선순위로 적용됩니다:

```
챗봇 JSON 설정 > 환경변수 기본값
```

| 설정 항목 | JSON 경로 | 환경변수 폴백 |
|----------|----------|------------|
| 모델 | `capabilities.model` 또는 `llm.model` | `LLM_DEFAULT_MODEL` |
| 온도 | `policy.temperature` 또는 `llm.temperature` | `LLM_DEFAULT_TEMPERATURE` |
| 최대 토큰 | `policy.max_tokens` 또는 `llm.max_tokens` | `LLM_DEFAULT_MAX_TOKENS` |

---

## 8. 로깅

FastAPI 기본 로깅 사용. `DEBUG=true` 시 SQL 쿼리도 출력됩니다.

위임 디버깅을 위한 상세 로그가 포함됩니다:
- 검색 결과 수 및 신뢰도 점수
- 위임 결정 사유 및 대상 챗봇
- LLM 응답 청크 수

---

## 9. 프로덕션 체크리스트

- [ ] `SECRET_KEY` 강력한 랜덤값으로 변경 (`openssl rand -base64 32`)
- [ ] `USE_MOCK_DB=false` + PostgreSQL 연결 설정
- [ ] `USE_MOCK_AUTH=false` + SSO 연결 설정
- [ ] `DEBUG=false`
- [ ] `SSL_VERIFY` 내부 CA 인증서 경로로 설정 (필요 시)
- [ ] `LLM_BASE_URL` 실제 LLM 서버 주소로 변경
- [ ] `INGESTION_BASE_URL` 실제 Ingestion 서버 주소로 변경
- [ ] PostgreSQL 스키마 생성 (`schema.sql`, `schema_conversation.sql`)
- [ ] 사용자 권한 초기 데이터 입력
