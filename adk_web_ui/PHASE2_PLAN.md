# ADK Web UI Phase 2 분석 및 실행 계획

## 📋 현재 상태 분석

### 구현된 기능 (Phase 1)
- `index_db.html`: 사이드바 + 채팅 UI, 세션 자동 로드, 초기화 버튼
- `server_db.py`: PostgreSQL 연동, 메시지/세션/위임체인 저장
- `server_sqlite.py`: SQLite 테스트 서버

### 현재 저장 구조의 문제점
```python
sessions table:
  - session_id (PK)
  - created_at
  - updated_at
  - initial_agent
  - is_active
  # ❌ knox_id가 없음! - 사용자별 데이터 분리 불가
```

---

## 🎯 Phase 2 요구사항 분석

### 1. 추가 개선사항 (UI/UX, 기능, 코드 품질)

#### UI/UX 개선사항
| 우선순위 | 항목 | 설명 |
|---------|------|------|
| P1 | 메시지 입력 개선 | 텍스트에리어로 변경 (멀티라인 지원), Shift+Enter 줄바꿈 |
| P1 | 로딩 상태 개선 | 스켈레톤 UI, 전송 중 인디케이터 |
| P2 | 에러 처리 개선 | 토스트 알림, 재시도 버튼 |
| P2 | 빈 화면 개선 | Agent 선택 시 빠른 시작 가이드 |
| P2 | 모바일 반응형 | 사이드바 토글, 터치 최적화 |
| P3 | 다크모드 지원 | 시스템 설정 연동 |
| P3 | 키보드 단축키 | Cmd/Ctrl+Enter 전송, ESC 닫기 |

#### 기능 개선사항
| 우선순위 | 항목 | 설명 |
|---------|------|------|
| P1 | 메시지 검색 | 세션 내 메시지 검색 기능 |
| P1 | 세션 이름 변경 | 사용자가 세션 이름 커스텀 가능 |
| P2 | 파일 첨부 | 이미지/문서 첨부 (Mock 또는 실제) |
| P2 | 메시지 복사/삭제 | 개별 메시지 관리 |
| P2 | 무한 스크롤 | 메시지 많을 때 페이지네이션 |
| P3 | 익스포트 | 대화 내역 다운로드 (JSON/TXT) |
| P3 | 읽음 확인 | 메시지 상태 표시 |

#### 코드 품질 개선
| 우선순위 | 항목 | 설명 |
|---------|------|------|
| P1 | 입력 검증 강화 | Pydantic validator 추가 |
| P1 | 에러 로깅 | 구조화된 로깅 (structured logging) |
| P2 | API 문서화 | OpenAPI/Swagger 메타데이터 |
| P2 | 설정 외부화 | config.py 또는 .env 분리 |
| P2 | 테스트 코드 | 단위/통합 테스트 추가 |
| P3 | 타입 힌트 | 전체 코드에 타입 어노테이션 |
| P3 | 코드 분리 | 라우터/서비스/리포지토리 분리 |

---

### 2. 관리자 기능 설계

#### 필요한 기능
| 기능 | 설명 | 구현 방식 |
|------|------|-----------|
| **대시보드** | 전체 통계 | 총 세션 수, 메시지 수, 활성 사용자 |
| **사용자 관리** | Knox ID별 조회 | 특정 사용자의 모든 세션 조회 |
| **세션 관리** | 전체 세션 조회/삭제 | 필터링, 일괄 삭제 |
| **Agent 통계** | Agent별 사용량 | 위임 체인 분석 |
| **시스템 상태** | DB 상태, API 상태 | 헬스체크 엔드포인트 |

#### URL 구조
```
일반 사용자:
  GET  /                    -> index_db.html (기존)
  GET  /api/sessions        -> 본인 세션만 (knox_id 필터)
  
관리자:
  GET  /admin               -> admin.html (관리자 대시보드)
  GET  /admin/login         -> 관리자 로그인 페이지
  
  GET  /api/admin/stats     -> 전체 통계
  GET  /api/admin/sessions  -> 모든 세션 조회 (관리자용)
  GET  /api/admin/users     -> 사용자 목록
  GET  /api/admin/user/{knox_id}/sessions  -> 특정 사용자 세션
  DELETE /api/admin/session/{id}          -> 세션 강제 삭제
```

#### 권한 체크 방법

**옵션 A: JWT 기반 (추천)**
```python
# 관리자 JWT 발급 (별도 로그인)
POST /api/admin/login
-> { "token": "eyJ...", "expires": "..." }

# API에서 검증
dependencies=[require_admin]
```

**옵션 B: 세션 기반 (간단)**
```python
# HTTP-only 쿠키로 관리자 세션 유지
# 내부적으로 관리자 Knox ID 목록 확인
ADMIN_KNOX_IDS = ["admin1", "admin2"]  # 환경변수로
```

**옵션 C: 헤더 기반 (데모용)**
```python
# X-Admin-Key 헤더로 간단 인증
# 개발/데모 환경에 적합
```

**추천: 옵션 B (Phase 2 MVP)** - 환경변수로 관리자 Knox ID 설정
```python
# .env
ADMIN_KNOX_IDS=knox_admin_001,knox_admin_002
```

---

### 3. Knox ID 기반 저장 구조 변경

#### 현재 스키마 → 변경 스키마

```sql
-- 기존 sessions 테이블 (문제: 사용자 구분 없음)
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_agent TEXT,
    is_active INTEGER DEFAULT 1
);

-- ✅ 변경된 sessions 테이블
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    knox_id TEXT NOT NULL,           -- ⭐ 추가: 사용자 식별
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initial_agent TEXT,
    is_active INTEGER DEFAULT 1,
    
    -- 인덱스 추가
    CONSTRAINT fk_knox_user FOREIGN KEY (knox_id) 
        REFERENCES users(knox_id) ON DELETE CASCADE
);

-- ⭐ 추가: users 테이블
CREATE TABLE users (
    knox_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    is_admin INTEGER DEFAULT 0       -- 관리자 여부
);

-- 인덱스 추가
CREATE INDEX idx_sessions_knox_id ON sessions(knox_id);
CREATE INDEX idx_users_is_admin ON users(is_admin);
```

#### API 변경사항

**Request 변경 (Knox ID 전달 필요)**
```python
# 기존
class ChatRequest(BaseModel):
    agent: str
    message: str
    session_id: str

# 변경
class ChatRequest(BaseModel):
    agent: str
    message: str
    session_id: str
    knox_id: str  # ⭐ 추가
```

**인증/인가 Flow**
```
1. 클라이언트는 Knox ID를 헤더 또는 바디로 전달
2. 서버는 Knox ID 검증 (형식 체크, 존재 여부)
3. 존재하지 않으면 users 테이블에 자동 생성
4. 세션 조회 시 knox_id로 필터링
5. 관리자는 is_admin=1인 경우 전체 데이터 접근 가능
```

**핵심 API 변경**
```python
# 세션 목록 - 본인 것만 조회
@app.get("/api/sessions")
async def list_sessions(knox_id: str = Header(...)):
    """본인 세션만 반환 (관리자는 전체)"""
    is_admin = check_admin(knox_id)
    if is_admin:
        return get_all_sessions()
    return get_sessions_by_knox(knox_id)

# 세션 히스토리 - 권한 체크
@app.get("/api/session/{session_id}/history")
async def get_history(session_id: str, knox_id: str = Header(...)):
    """세션 소유자 또는 관리자만 접근 가능"""
    session = get_session(session_id)
    if session['knox_id'] != knox_id and not check_admin(knox_id):
        raise HTTPException(403, "Access denied")
    return get_session_history(session_id)
```

#### 세션 조회 시 Knox ID 필터링

```python
# 변경 전
def get_all_sessions() -> List[Dict]:
    cursor.execute('SELECT * FROM sessions WHERE is_active = 1')
    
# 변경 후
def get_sessions_by_knox(knox_id: str) -> List[Dict]:
    """특정 사용자의 세션만 조회"""
    cursor.execute('''
        SELECT * FROM sessions 
        WHERE knox_id = %s AND is_active = 1
        ORDER BY updated_at DESC
    ''', (knox_id,))

def get_all_sessions(admin_knox_id: str) -> List[Dict]:
    """관리자용: 전체 세션 (옵션: knox_id로 필터링 가능)"""
    # 관리자 권한 확인 후 실행
    cursor.execute('''
        SELECT s.*, u.knox_id 
        FROM sessions s
        JOIN users u ON s.knox_id = u.knox_id
        WHERE s.is_active = 1
        ORDER BY s.updated_at DESC
    ''')
```

---

## 📅 실행 계획 및 우선순위

### Phase 2-1: Knox ID 통합 (Week 1) - 🔴 최우선

| Day | 작업 | 파일 |
|-----|------|------|
| 1 | DB 스키마 변경 | `schema_v2.sql` |
| 2 | models.py 생성 (Pydantic 모델) | `models.py` |
| 3 | 데이터베이스 레이어 분리 | `database.py` |
| 4 | Knox ID 미들웨어 구현 | `middleware.py` |
| 5 | API 엔드포인트 Knox ID 적용 | `server_db.py` 수정 |
| 6 | Frontend Knox ID 연동 | `index_db.html` 수정 |
| 7 | 테스트 및 버그 수정 | - |

**산출물:**
- Knox ID 기반 세션 분리 완료
- 사용자별 데이터 격리 확인

### Phase 2-2: 관리자 기능 (Week 2)

| Day | 작업 | 파일 |
|-----|------|------|
| 1 | 관리자 권한 체크 로직 | `auth.py` |
| 2 | 관리자 API 구현 | `admin_routes.py` |
| 3 | 통계 쿼리 작성 | `database.py` |
| 4 | 관리자 페이지 HTML | `admin.html` |
| 5 | 관리자 페이지 CSS/JS | `admin.js`, `admin.css` |
| 6 | 통합 테스트 | - |
| 7 | 문서화 | `README.md` |

**산출물:**
- `/admin` 대시보드
- 관리자 API (`/api/admin/*`)

### Phase 2-3: UI/UX 개선 (Week 3)

| Day | 작업 | 우선순위 |
|-----|------|----------|
| 1-2 | 텍스트에리어 + 멀티라인 | P1 |
| 3 | 스켈레톤 로딩 | P1 |
| 4 | 토스트 알림 | P2 |
| 5 | 세션 이름 변경 | P2 |
| 6 | 메시지 검색 | P2 |
| 7 | 모바일 반응형 | P2 |

**산출물:**
- 개선된 `index_db.html`

### Phase 2-4: 코드 품질 (Week 4)

| Day | 작업 | 파일 |
|-----|------|------|
| 1-2 | 설정 외부화 | `config.py`, `.env` |
| 3 | 구조화된 로깅 | `logging_config.py` |
| 4 | API 문서화 | docstring, OpenAPI |
| 5-6 | 코드 분리 (라우터) | `routes/` 디렉토리 |
| 7 | 테스트 코드 작성 | `tests/` |

---

## 📁 파일 구조 (Target)

```
adk_web_ui/
├── main.py                    # FastAPI 앱 진입점
├── config.py                  # 설정 관리
├── database.py                # DB 연결 및 ORM
├── models.py                  # Pydantic 모델
├── auth.py                    # 인증/인가
├── middleware.py              # 미들웨어
├── logging_config.py          # 로깅 설정
├── requirements.txt           # 의존성
│
├── routes/
│   ├── __init__.py
│   ├── chat.py               # 채팅 API
│   ├── sessions.py           # 세션 API
│   └── admin.py              # 관리자 API
│
├── static/
│   ├── index.html            # 메인 UI
│   ├── admin.html            # 관리자 UI
│   ├── css/
│   │   ├── main.css
│   │   └── admin.css
│   └── js/
│       ├── main.js
│       ├── admin.js
│       └── components.js
│
├── tests/
│   ├── test_api.py
│   ├── test_auth.py
│   └── test_database.py
│
└── sql/
    ├── schema_v1.sql         # 현재 스키마
    ├── schema_v2.sql         # Knox ID 추가
    └── migrations/
        └── 001_add_knox_id.py
```

---

## 🚀 즉시 실행 가능한 작업 (Quick Wins)

### 1. DB 마이그레이션 스크립트 (오늘)
```sql
-- migration_v1_to_v2.sql
-- Knox ID 추가 마이그레이션

-- 1. users 테이블 생성
CREATE TABLE users (
    knox_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP,
    is_admin INTEGER DEFAULT 0
);

-- 2. sessions 테이블에 knox_id 컬럼 추가
ALTER TABLE sessions ADD COLUMN knox_id TEXT;

-- 3. 기존 데이터 마이그레이션 (임시 knox_id)
UPDATE sessions SET knox_id = 'legacy_user' WHERE knox_id IS NULL;

-- 4. NOT NULL 제약조건 추가
ALTER TABLE sessions ALTER COLUMN knox_id SET NOT NULL;

-- 5. 인덱스 생성
CREATE INDEX idx_sessions_knox_id ON sessions(knox_id);
CREATE INDEX idx_users_is_admin ON users(is_admin);

-- 6. 외래키 제약조건 (선택)
-- ALTER TABLE sessions ADD CONSTRAINT fk_knox_user 
--     FOREIGN KEY (knox_id) REFERENCES users(knox_id);
```

### 2. 환경변수 설정 (.env)
```bash
# .env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=adk_chat
DB_USER=postgres
DB_PASSWORD=password

# 관리자 설정
ADMIN_KNOX_IDS=admin001,admin002
DEFAULT_USER_KNOX_ID=anonymous

# 앱 설정
APP_NAME="ADK Web UI"
DEBUG=false
LOG_LEVEL=INFO
```

### 3. Knox ID 전달용 헤더 정의
```javascript
// Frontend에서 Knox ID 전달
const headers = {
    'Content-Type': 'application/json',
    'X-Knox-Id': currentUser.knoxId || 'anonymous'
};

fetch('/api/sessions', { headers });
```

---

## ⚠️ 리스크 및 고려사항

| 리스크 | 영향 | 대책 |
|--------|------|------|
| 기존 데이터 마이그레이션 | 높음 | `knox_id='legacy'`로 기본값 설정 |
| Knox ID 없는 요청 | 중간 | anonymous 사용자 자동 생성 |
| 관리자 설정 누락 | 중간 | 시작 시 경고 로그 출력 |
| 세션 공유 문제 | 높음 | Knox ID 필수화, 권한 체크 강화 |
| 성능 저하 | 낮음 | 인덱스 추가로 커버 |

---

## ✅ 체크리스트

### Phase 2-1 완료 기준
- [ ] DB 스키마 v2 적용
- [ ] 모든 세션에 knox_id 할당
- [ ] API가 knox_id 헤더/파라미터 수신
- [ ] 세션 조회가 knox_id로 필터링
- [ ] 관리자 권한 체크 동작
- [ ] Frontend에서 knox_id 전송

### Phase 2-2 완료 기준
- [ ] `/admin` 페이지 접속 가능
- [ ] 관리자 대시보드 통계 표시
- [ ] 전체 세션 조회 가능
- [ ] 사용자별 세션 필터링

---

**작성일:** 2026-04-22  
**다음 리뷰:** Phase 2-1 완료 후
