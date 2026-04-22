# ADK Web UI 사용 가이드

## 개요
ADK Agent를 웹 UI로 관리하고 테스트할 수 있는 대체 인터페이스입니다.
(ADK Web의 Angular 프론트엔드 버그를 우회하기 위해 직접 구현)

---

## 🚀 빠른 시작

### 1. Mock 모드 서버 실행 (API 키 불필요)

```bash
# 가상환경 활성화
source .venv/bin/activate

# Mock 모드 서버 실행
python3 adk_web_ui/server_mock.py
```

### 2. 웹 브라우저에서 접속

```
http://localhost:8090
```

---

## 📁 파일 구조

```
adk_web_ui/
├── index.html              # 웹 UI (vanilla JS)
├── server_mock.py          # Mock 모드 서버
├── server_debug.py         # 디버그 모드 (Content 객체 테스트)
├── server_debug_v2.py      # Runner API 테스트
├── server_fixed.py         # Runner with Content
└── server_cli.py           # adk run CLI 모드
```

---

## 🖥️ 서버 모드별 실행 방법

### 1. Mock 모드 (권장)
**실제 API 호출 없이 내부 로직 테스트**

```bash
python3 adk_web_ui/server_mock.py
```
- 포트: 8090
- 특징: 위임 체인, 세션 관리 테스트 가능
- 응답: Mock 응답 (실제 LLM 호출 없음)

**위임 규칙:**
- "인사", "휴가", "급여", "복지" → `chatbot_hr_adk`
- "기술", "개발", "시스템", "버그" → `chatbot_tech_adk`

---

### 2. CLI 모드
**`adk run` 명령어를 서브프로세스로 실행**

```bash
python3 adk_web_ui/server_cli.py
```
- 포트: 8089
- 특징: 실제 ADK CLI 사용
- 단점: 대화형이라 서브프로세스 동작 불안정

---

### 3. Debug 모드
**Content 객체 생성 및 Runner API 테스트**

```bash
python3 adk_web_ui/server_debug_v2.py
```
- 포트: 8088
- 특징: 디테일한 로깅
- 필요: Gemini API 키 (없으면 오류)

---

## 🌐 API 엔드포인트

### Agent 목록 조회
```bash
GET http://localhost:8090/list-apps
```

**응답 예시:**
```json
["chatbot_company_adk", "chatbot_hr_adk", "chatbot_tech_adk"]
```

---

### Agent 상세 정보
```bash
GET http://localhost:8090/api/agents/detail
```

**응답 예시:**
```json
[
  {
    "id": "chatbot_company_adk",
    "name": "회사 전체 지원",
    "description": "모든 사내 문의 처리",
    "level": 0,
    "sub_agents": ["chatbot_hr_adk", "chatbot_tech_adk"]
  }
]
```

---

### 메시지 전송 (Agent 실행)
```bash
POST http://localhost:8090/api/run
Content-Type: application/json

{
  "agent": "chatbot_company_adk",
  "message": "휴가 신청 방법 알려주세요",
  "session_id": "unique_session_id"
}
```

**응답 예시:**
```json
{
  "response": "[인사지원] 응답 (Mock Mode)...",
  "session_id": "unique_session_id",
  "agent_used": "chatbot_hr_adk",
  "delegation_chain": ["chatbot_company_adk", "chatbot_hr_adk"],
  "debug_info": {
    "original_agent": "chatbot_company_adk",
    "delegated_agent": "chatbot_hr_adk",
    "delegation_reason": "키워드 '휴가' 감지"
  }
}
```

---

### 세션 목록 조회
```bash
GET http://localhost:8090/api/sessions
```

**응답 예시:**
```json
{
  "sessions": [
    {
      "id": "test_12345",
      "message_count": 4,
      "delegation_chain": ["chatbot_company_adk", "chatbot_hr_adk"]
    }
  ]
}
```

---

### 세션 히스토리 조회
```bash
GET http://localhost:8090/api/session/{session_id}/history
```

**응답 예시:**
```json
{
  "session_id": "test_12345",
  "history": [
    {"role": "user", "content": "안녕하세요", "agent": "chatbot_company_adk"},
    {"role": "assistant", "content": "[회사 전체 지원] 응답...", "agent": "chatbot_company_adk"}
  ],
  "delegation_chain": ["chatbot_company_adk", "chatbot_hr_adk"]
}
```

---

### 디버그 로그 조회
```bash
GET http://localhost:8090/api/debug/logs?lines=50
```

---

## 🧪 테스트 방법

### Python 스크립트로 테스트
```bash
# Mock 모드 전체 테스트
python3 test_mock_full.py

# CLI API 테스트
python3 test_cli_api.py
```

### curl로 테스트
```bash
# Agent 목록
curl http://localhost:8090/list-apps

# 메시지 전송
curl -X POST http://localhost:8090/api/run \
  -H "Content-Type: application/json" \
  -d '{"agent":"chatbot_company_adk","message":"안녕하세요","session_id":"test_001"}'
```

---

## 🔧 문제 해결

### 포트 충돌
```bash
# 다른 포트로 실행
# server_mock.py 파일에서 port 번호 변경
uvicorn.run(app, host="0.0.0.0", port=8091)  # 8091로 변경
```

### 모듈 Import 에러
```bash
# 가상환경 확인
which python3

# 패키지 설치 확인
pip list | grep google-adk
```

---

## 📝 참고 사항

- **ADK Web UI vs Mock 서버**: ADK Web (`adk web`)는 Angular 프론트엔드 버그로 Agent 목록 표시 안 됨
- **API 키 필요 여부**: Mock 모드는 실제 LLM 호출 없이 테스트 가능
- **위임 체인**: Root Agent → Sub Agent 위임 로직 테스트 가능
- **세션 관리**: 메시지 히스토리 및 위임 체인 저장/조회 가능

---

## 🔗 관련 파일

- `memory/2026-04-22.md` - 상세 개발 기록
- `adk_agents/` - Agent 정의 파일
