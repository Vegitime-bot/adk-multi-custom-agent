# ADK Multi Custom Agent

Google ADK 기반 멀티 테넌트 RAG 챗봇 플랫폼

Forked from multi-custom-agent

---

## 빠른 시작

### 1. 환경 설정

```bash
cd adk-multi-custom-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Mock Ingestion 서버 실행 (검색 기능 테스트용)

```bash
# 별도 터미널에서 실행
python3 -m uvicorn mock_ingestion_server:app --host 0.0.0.0 --port 8001 --reload
# → http://localhost:8001

# 또는 백그라운드 실행
nohup python3 -m uvicorn mock_ingestion_server:app --host 0.0.0.0 --port 8001 > logs/mock_ingestion.log 2>&1 &
echo $! > logs/mock_ingestion.pid
```

**Mock 데이터 목록:**
| DB ID | 설명 |
|-------|------|
| `db_hr_policy` | 인사평가제도, 규정 |
| `db_hr_benefit` | 급여, 복리후생 |
| `db_hr_overview` | 인사팀 개요 |
| `db_tech_overview` | 기술지원팀 개요 |
| `db_backend` | 백엔드 개발 |
| `db_frontend` | 프론트엔드 개발 |

### 3. 메인 서버 실행

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --reload
# → http://localhost:8080
```

### 4. 접속

| URL | 설명 |
|-----|------|
| `http://localhost:8080` | 챗봇 UI |
| `http://localhost:8080/admin` | 관리자 패널 |
| `http://localhost:8080/docs` | API 문서 (Swagger) |
| `http://localhost:8080/health` | 헬스체크 |

---

## API 테스트

### 헬스체크
```bash
curl http://localhost:8080/health
```

### 챗봇 목록 조회
```bash
curl http://localhost:8080/api/chatbots
```

### 세션 생성
```bash
curl -X POST http://localhost:8080/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"chatbot_id": "chatbot-company"}'
```

### 채팅 (SSE 스트리밍)
```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "chatbot_id": "chatbot-company",
    "message": "안녕하세요",
    "session_id": "<세션_ID>"
  }'
```

---

## 주요 설정

`.env` 파일에서 설정:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `USE_MOCK_DB` | `true` | `false` → PostgreSQL 사용 |
| `USE_MOCK_AUTH` | `true` | `false` → SSO 인증 사용 |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM API 엔드포인트 |
| `INGESTION_BASE_URL` | `http://localhost:8001` | 벡터 검색 서버 |
| `PORT` | `8080` | 서버 포트 |
| `USE_ADK` | `false` | `true` → Google ADK 사용 |

---

## 계층적 위임 구조

```
회사 전체 지원 챗봇 (L0)
├── 인사지원 상위 챗봘 (L1)
│   ├── 복리후생 전문 챗봇 (L2)
│   └── 인사정책 전문 챗봇 (L2)
└── 기술지원 상위 챗봇 (L1)
    ├── 백엔드 개발 전문 챗봇 (L2)
    ├── 프론트엔드 개발 전문 챗봇 (L2)
    └── DevOps 인프라 전문 챗봇 (L2)
```

---

## Python 버전

- **개발 환경**: Python 3.9+
- **사내 서버**: Python 3.10+ 권장

---

## 문서

- [API 명세](docs/03_API_SPECIFICATION.md)
- [설정 & 배포](docs/05_CONFIGURATION.md)
- [테스트](docs/06_TESTING.md)
