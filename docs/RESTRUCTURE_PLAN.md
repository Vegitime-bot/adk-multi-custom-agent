# Multi Custom Agent Service - 구조 변경 계획

## 변경 목적

사내 SSO 템플릿 구조에 맞춰 프로젝트 구조 변경
- 템플릿: `app.py` + `config.py` 루트 위치, `uvicorn.run(app, ...)` 직접 실행

---

## 현재 구조

```
multi-custom-agent/
├── backend/
│   ├── main.py          # FastAPI 앱 (이 방식으로 실행)
│   ├── config.py        # 설정
│   ├── api/
│   ├── auth/
│   ├── database/
│   ├── permissions/
│   └── ...
├── chatbots/
├── static/
└── requirements.txt
```

**실행 방식:** `uvicorn backend.main:app --host 0.0.0.0 --port 8080`

---

## 목표 구조

```
multi-custom-agent/
├── app.py               # 메인 앱 (루트, SSO 템플릿 형식)
├── config.py            # 설정 (루트)
├── backend/             # 비즈니스 로직
│   ├── config.py        # 루트 config 재export
│   ├── api/
│   ├── auth/
│   ├── database/
│   ├── permissions/
│   └── ...
├── chatbots/
├── static/
└── requirements.txt
```

**실행 방식:** `python app.py` (또는 `uvicorn app:app`)

---

## 변경 작업 목록

### Phase 1: 파일 이동/생성 (완료됨)

- [x] `app.py` 루트에 생성 - FastAPI 앱 팩토리 패턴
- [x] `config.py` 루트에 생성 - 설정 클래스
- [x] `backend/config.py` 수정 - 루트 config 재export

### Phase 2: Import 경로 수정

- [ ] `backend/database/session.py` - config import 경로 확인
- [ ] `backend/permissions/repository.py` - config import 경로 확인
- [ ] `backend/api/*.py` - config import 경로 확인
- [ ] 기타 `backend/**` 파일들 - import 경로 일괴 확인

### Phase 3: 기존 파일 정리

- [ ] `backend/main.py` - deprecated 표시 또는 제거
- [ ] `backend/config.py` - 순환 import 방지 검증

### Phase 4: SSO 통합 준비

- [ ] `app.py`에 SSO middleware placeholder 추가
- [ ] `backend/auth/`에 SSO handler 준비
- [ ] 환경변수 추가 (SSO_CLIENT_ID, SSO_CLIENT_SECRET 등)

---

## Test Plan

### 1. 기본 실행 테스트
```bash
# 새 방식 실행
cd multi-custom-agent
python app.py

# 또는
uvicorn app:app --host 0.0.0.0 --port 8080
```

**검증:**
- [ ] 서버 정상 시작 (port 8080)
- [ ] Health check 응답: `{"status":"ok",...}`
- [ ] 로그에 "챗봇 N개 로드됨" 출력

### 2. API 동작 테스트
```bash
# 1. Health
curl http://localhost:8080/health

# 2. 챗봇 목록
curl http://localhost:8080/api/chatbots

# 3. 권한 API
curl http://localhost:8080/api/permissions/admin/stats

# 4. Admin 페이지
curl http://localhost:8080/admin
```

**검증:**
- [ ] 모든 API 200 응답
- [ ] JSON 파싱 오류 없음
- [ ] Static 파일 서빙 정상

### 3. 기존 코드 하위호환 테스트
```bash
# 기존 방식도 여전히 동작해야 함
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

**검증:**
- [ ] 기존 방식으로도 실행 가능 (선택사항)

### 4. SSO 통합 테스트 (Phase 4 이후)
```bash
# 환경변수 설정
export USE_MOCK_AUTH=false
export SSO_CLIENT_ID=xxx
export SSO_CLIENT_SECRET=xxx
export SSO_REDIRECT_URI=http://localhost:8080/auth/callback

python app.py
```

**검증:**
- [ ] `/login` 엔드포인트에서 SSO 로그인 페이지로 redirect
- [ ] `/auth/callback`에서 토큰 정상 수신
- [ ] 세션에 사용자 정보 저장

---

## 롤백 계획

문제 발생 시 롤백 방법:
```bash
# Git으로 복구
git checkout HEAD -- backend/main.py backend/config.py
rm app.py config.py  # 신규 파일 삭제

# 또는 기존 방식으로 실행
uvicorn backend.main:app --port 8080
```

---

## 일정

| Phase | 예상 소요 | 담당 |
|-------|----------|------|
| Phase 1 | ✅ 완료 | - |
| Phase 2 | 30분 | Agent |
| Phase 3 | 15분 | Agent |
| Phase 4 | 1시간 | Agent (별도 PR) |

---

## 결정사항

### 질문:
1. **기존 `backend/main.py` 유지 여부**
   - A) 완전히 삭제
   - B) deprecated 표시 후 유지 (하위호환)
   - C) `app.py`에서 import만 하는 thin wrapper로 변경

2. **SSO 작업 시기**
   - A) 구조 변경 완료 후 즉시 진행
   - B) 구조 변경 검증 후 별도 PR로 진행

3. **테스트 범위**
   - A) Mock DB만 테스트 (빠름)
   - B) 실제 PostgreSQL 연결 테스트 필요 (느림)

---

*작성: 2026-04-03*
*상태: Phase 1 완료, Phase 2 대기*
