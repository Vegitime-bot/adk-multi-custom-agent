# 06. 테스트 가이드 (Testing)

## 1. 테스트 전략

이 프로젝트는 통합 테스트 중심으로 구성되어 있습니다.

| 테스트 유형 | 도구 | 설명 |
|-----------|------|------|
| 통합 테스트 | pytest + pytest-asyncio | API 엔드포인트 전체 흐름 |
| E2E 웹 테스트 | pytest | 웹 페이지 접속 및 UI 동작 |
| 관리자 패널 테스트 | pytest | 챗봇 CRUD, 계층 뷰 |

> 단위 테스트(Unit Test)는 현재 별도로 작성되어 있지 않으며, 통합 테스트로 주요 기능을 커버합니다.

---

## 2. 테스트 환경 요구사항

- Python 3.9+
- pytest 8.3.4
- pytest-asyncio 0.24.0
- 실행 중인 Mock Ingestion 서버 (`python mock_ingestion_server.py`)
- 실행 중인 메인 서버 (`python app.py`)

---

## 3. 테스트 실행 방법

### 3.1 전체 테스트 실행

```bash
# 가상환경 활성화
source .venv/bin/activate

# 서버가 실행 중인지 확인 (별도 터미널에서)
# python mock_ingestion_server.py  # 포트 8001
# python app.py                    # 포트 8080

# 테스트 실행
pytest tests/ -v
```

### 3.2 특정 테스트 파일 실행

```bash
# 웹 페이지 테스트
pytest tests/test_web_pages.py -v

# 관리자 패널 테스트
pytest tests/test_admin_panel.py -v
```

### 3.3 특정 테스트 케이스 실행

```bash
pytest tests/test_web_pages.py::test_chatbot_ui_loads -v
pytest tests/test_admin_panel.py::test_create_chatbot -v
```

### 3.4 상세 출력 옵션

```bash
# 로그 출력 포함
pytest tests/ -v -s

# 실패 시 즉시 중단
pytest tests/ -v -x

# 실패 이유 상세 출력
pytest tests/ -v --tb=long
```

---

## 4. 현재 테스트 파일

### 4.1 tests/test_web_pages.py

웹 UI 관련 E2E 테스트.

**테스트 대상:**
- 메인 페이지 접속 (`GET /`)
- 관리자 페이지 접속 (`GET /admin`)
- 챗봇 UI 로드 확인
- URL 파라미터 기반 챗봇 자동 선택

**주요 테스트 케이스:**

```python
def test_main_page_loads():
    """메인 페이지가 정상적으로 로드되는지 확인"""

def test_admin_page_loads():
    """관리자 패널이 정상적으로 로드되는지 확인"""

def test_health_check():
    """헬스체크 엔드포인트 응답 확인"""

def test_chatbot_selection_from_url():
    """URL 파라미터로 챗봇 자동 선택"""
```

---

### 4.2 tests/test_admin_panel.py

관리자 패널 기능 통합 테스트.

**테스트 대상:**
- 챗봇 CRUD (생성, 조회, 수정, 삭제)
- 챗봇 계층 구조 뷰
- 사용자 권한 관리
- 통계 대시보드

**주요 테스트 케이스:**

```python
def test_list_chatbots():
    """챗봇 목록 조회 테스트"""

def test_create_chatbot():
    """새 챗봇 생성 및 검증"""

def test_update_chatbot():
    """챗봇 정의 수정"""

def test_delete_chatbot():
    """챗봇 삭제 및 파일 제거 확인"""

def test_hierarchy_view():
    """챗봇 계층 구조 표시 확인"""

def test_permission_management():
    """사용자-챗봇 권한 CRUD"""
```

---

## 5. 과거 테스트 파일 (삭제됨)

다음 테스트 파일들은 개발 과정에서 삭제되었습니다:

| 파일 | 내용 | 삭제 사유 |
|------|------|----------|
| `test_conversations.py` | 대화 기록 API 테스트 | 리팩토링 |
| `test_delegation_with_enhanced_db.py` | 위임 로직 + Mock DB 테스트 | 통합 |
| `test_e2e_browser.py` | 브라우저 E2E 테스트 | 정리 |
| `test_embedding_delegation.py` | 임베딩 기반 위임 테스트 | 통합 |
| `test_hierarchical_delegation.py` | 계층적 위임 테스트 | 통합 |
| `test_parent_child_delegation.py` | 부모-자식 위임 테스트 | 통합 |
| `test_parent_child_integration.py` | 부모-자식 통합 테스트 | 통합 |
| `test_stage3_stage4_api.py` | Stage 3/4 API 테스트 | 통합 |
| `test_stage3_stage4_web.py` | Stage 3/4 웹 테스트 | 통합 |

---

## 6. 수동 테스트 방법

### 6.1 챗봇 대화 테스트 (curl)

```bash
# Tool 모드 (무상태)
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "chatbot_id": "chatbot-a",
    "message": "안녕하세요",
    "mode": "tool"
  }' \
  --no-buffer

# Agent 모드 (대화형)
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "chatbot_id": "chatbot-hr",
    "message": "연차는 몇 일인가요?",
    "mode": "agent"
  }' \
  --no-buffer

# 계층적 위임 테스트 (HR 상위 챗봇)
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "chatbot_id": "chatbot-hr",
    "message": "복리후생 제도에 대해 알려주세요"
  }' \
  --no-buffer
```

### 6.2 권한 확인 테스트

```bash
# 사용자 권한 목록
curl http://localhost:8080/api/permissions/users/user-001

# 특정 챗봇 접근 권한 확인
curl http://localhost:8080/api/permissions/check/chatbot-hr
```

### 6.3 헬스체크

```bash
curl http://localhost:8080/health
# 예상 응답: {"status":"ok","use_mock_db":true,...}
```

### 6.4 세션 및 히스토리

```bash
# 세션 생성
curl -X POST http://localhost:8080/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"chatbot_id": "chatbot-hr"}'

# 대화 후 히스토리 조회
curl http://localhost:8080/api/sessions/{session_id}/history
```

---

## 7. Mock Ingestion 서버

> 파일: `mock_ingestion_server.py`

실제 벡터 검색 서버 없이 테스트할 수 있는 Mock 서버입니다.

**기능:**
- 도메인별 샘플 데이터 반환 (HR, Tech, RTL)
- 키워드 매칭 기반 결과 필터링
- `x-api-key` 헤더 검증

**실행:**

```bash
python mock_ingestion_server.py
# → http://localhost:8001 에서 실행
```

**지원 DB 도메인:**
- `db_hr_*`: HR 관련 (연차, 급여, 복리후생, 인사 정책)
- `db_tech_*`: 기술 (FastAPI, Docker, 데이터베이스)
- `db_rtl_*`: RTL/Verilog 설계

---

## 8. 테스트 데이터 정리

테스트 중 생성된 임시 챗봇 파일이 `chatbots/` 디렉토리에 남을 수 있습니다.

```bash
# 테스트용 임시 파일 확인
ls chatbots/test-* chatbots/hierarchy-test-*

# 정리 (실제 챗봇 파일은 삭제하지 않도록 주의)
rm -f chatbots/test-*.json chatbots/hierarchy-test-*.json chatbots/test-remove-*.json
```

---

## 9. 테스트 커버리지 현황

| 기능 | 커버리지 | 비고 |
|------|---------|------|
| 챗봇 대화 (SSE) | 통합 테스트 | test_web_pages.py |
| 챗봇 CRUD | 통합 테스트 | test_admin_panel.py |
| 계층적 위임 | 수동 테스트 | curl 명령으로 검증 |
| SSO 인증 | 수동 테스트 | 실제 SSO 환경 필요 |
| 권한 관리 | 통합 테스트 | test_admin_panel.py |
| PostgreSQL 연동 | 수동 테스트 | DB 환경 필요 |
| LLM 스트리밍 | 수동 테스트 | LLM 서버 필요 |
