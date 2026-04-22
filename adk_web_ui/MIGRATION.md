# ADK Web UI Phase 2 Migration Guide

## 📋 개요

Phase 2에서는 Knox ID 기반 사용자 분리와 관리자 기능이 추가되었습니다.

### 주요 변경사항
- ✅ Knox ID 기반 세션/메시지 저장
- ✅ 사용자별 데이터 격리
- ✅ 관리자 대시보드
- ✅ 관리자 API (`/api/admin/*`)

---

## 🚀 마이그레이션 절차

### 1. 백업 (중요!)

```bash
# PostgreSQL 백업
pg_dump -U postgres adk_chat > adk_chat_backup.sql

# 또는 SQLite 사용시
cp adk_chat.db adk_chat_backup.db
```

### 2. 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env
```

**필수 설정:**
```bash
# 관리자 Knox ID 설정 (쉼표로 구분)
ADMIN_KNOX_IDS=your_admin_knox_id_here

# Knox ID 필수 여부
REQUIRE_KNOX_ID=true

# 기본 Knox ID (인증 실패시)
DEFAULT_KNOX_ID=anonymous
```

### 3. DB 마이그레이션

#### PostgreSQL
```bash
# 마이그레이션 스크립트 실행
psql -U postgres -d adk_chat -f sql/migration_v1_to_v2.sql

# 결과 확인
psql -U postgres -d adk_chat -c "SELECT * FROM users;"
psql -U postgres -d adk_chat -c "SELECT knox_id, COUNT(*) FROM sessions GROUP BY knox_id;"
```

#### SQLite (개발용)
```bash
# 기존 DB 삭제 (또는 백업)
mv adk_chat.db adk_chat_v1.db

# 새 스키마 적용
sqlite3 adk_chat.db < sql/schema_v2.sql
```

### 4. 새 서버 실행

```bash
# 의존성 확인
pip install pydantic-settings

# 서버 실행 (port 8093)
python server_v2.py
```

### 5. Frontend 업데이트

```bash
# 새 HTML 파일 사용
cp index_v2.html index.html

# 또는 기존 index_db.html 대체
```

---

## 🔧 API 변경사항

### 새 헤더 필수

모든 API 요청에 `X-Knox-Id` 헤더가 필요합니다:

```javascript
fetch('/api/sessions', {
    headers: {
        'Content-Type': 'application/json',
        'X-Knox-Id': 'your_knox_id_here'
    }
});
```

### 엔드포인트

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/api/agents/detail` | Agent 목록 (인증 불필요) |
| POST | `/api/run` | 채팅 (X-Knox-Id 필수) |
| GET | `/api/sessions` | 본인 세션 목록 |
| GET | `/api/session/{id}/history` | 세션 히스토리 |
| POST | `/api/session/reset` | 세션 초기화 |
| DELETE | `/api/session/{id}` | 세션 삭제 |

### 관리자 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/api/admin/stats` | 전체 통계 |
| GET | `/api/admin/users` | 사용자 목록 |
| GET | `/api/admin/sessions` | 전체 세션 |
| GET | `/api/admin/user/{id}/sessions` | 특정 사용자 세션 |
| POST | `/api/admin/user/{id}/admin` | 관리자 권한 설정 |

---

## 📁 파일 구조

```
adk_web_ui/
├── server_v2.py          # Phase 2 서버 (Knox ID + Admin)
├── index_v2.html         # Phase 2 Frontend
├── admin.html            # 관리자 대시보드
├── models.py             # Pydantic 모델
├── database.py           # DB 레이어
├── config.py             # 설정 관리
├── .env.example          # 환경변수 예시
├── .env                  # 실제 환경변수 (gitignore)
│
├── sql/
│   ├── schema_v2.sql              # 새 스키마
│   ├── migration_v1_to_v2.sql     # 마이그레이션 스크립트
│   └── schema.sql                 # 기존 스키마 (v1)
│
├── server_db.py          # Phase 1 서버 (보관용)
├── index_db.html         # Phase 1 Frontend (보관용)
└── server_sqlite.py      # Phase 1 SQLite (보관용)
```

---

## 🔄 롤백 (문제 발생시)

### DB 롤백
```bash
# PostgreSQL 백업 복원
psql -U postgres -d adk_chat -f adk_chat_backup.sql

# 또는 마이그레이션 취소
psql -U postgres -d adk_chat -f - <<EOF
-- 롤백
ALTER TABLE sessions DROP COLUMN IF EXISTS knox_id;
DROP TABLE IF EXISTS users CASCADE;
DROP INDEX IF EXISTS idx_sessions_knox_id;
DROP INDEX IF EXISTS idx_users_is_admin;
EOF
```

### 서버 롤백
```bash
# Phase 1 서버 실행
python server_db.py  # port 8091
```

---

## ⚠️ 주의사항

1. **Knox ID 필수**: `REQUIRE_KNOX_ID=true` 설정 시 모든 API에 `X-Knox-Id` 헤더 필요
2. **관리자 설정**: `ADMIN_KNOX_IDS`에 관리자 Knox ID를 설정해야 관리자 기능 사용 가능
3. **기존 데이터**: 마이그레이션 시 기존 세션은 `legacy_user` Knox ID로 할당됨
4. **권한 체크**: 이제 세션 조회/수정/삭제 시 Knox ID 기반 권한 체크 수행

---

## 🧪 테스트

```bash
# 테스트 스크립트 실행
curl -X POST http://localhost:8093/api/run \
  -H "Content-Type: application/json" \
  -H "X-Knox-Id: test_user_001" \
  -d '{
    "agent": "chatbot_company_adk",
    "message": "안녕하세요",
    "session_id": "test_session_001"
  }'

# 세션 조회
curl http://localhost:8093/api/sessions \
  -H "X-Knox-Id: test_user_001"
```

---

## 📞 지원

문제 발생 시:
1. `server_v2.py` 로그 확인
2. DB 연결 상태 확인
3. `.env` 설정 확인
4. 마이그레이션 스크립트 재실행
