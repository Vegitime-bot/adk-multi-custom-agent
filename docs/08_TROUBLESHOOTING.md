# 08. 문제 해결 가이드 (Troubleshooting)

## 1. Known Issues

### 1.1 `updated_at` 컬럼 오류

**증상:**
```
sqlalchemy.exc.ProgrammingError: column "updated_at" of relation "user_chatbot_access" does not exist
```

**원인:** `schema.sql`에 `updated_at` 컬럼이 정의되어 있지만, ORM 모델에서 제거됨 (커밋 `ede75cc`).

**해결:**
- 이미 수정됨. DB를 새로 생성하거나 `schema.sql`에서 `updated_at` 컬럼 제거.
- 기존 DB가 있다면: `ALTER TABLE test.user_chatbot_access DROP COLUMN IF EXISTS updated_at;`

---

### 1.2 SSO knox_id 파싱 실패

**증상:** SSO 로그인 후 챗봇 접근 시 권한 오류

**원인:** SSO 토큰에서 `knox_id` 추출 필드가 다를 수 있음

**해결:**
- `USE_MOCK_AUTH=true`로 설정하여 임시 우회 (커밋 `1cbf991` 참고)
- 실제 SSO 연동 시 `sso.py`의 `knox_id` 추출 필드를 SSO 서버 응답에 맞게 조정

---

### 1.3 LLM 스트리밍 `choices` 빈 리스트 에러

**증상:**
```
IndexError: list index out of range
# 또는
KeyError: choices
```

**원인:** LLM 서버가 빈 `choices` 배열을 반환하는 청크 전송 (커밋 `68941a8` 수정됨)

**해결:** 이미 방어 코드 적용됨. 재발 시 `backend/llm/client.py`의 스트리밍 루프 확인.

---

### 1.4 SQLAlchemy 2.0 raw SQL 오류

**증상:**
```
sqlalchemy.exc.RemovedIn20Warning: Textual SQL expression
```

**원인:** SQLAlchemy 2.0에서 raw SQL은 `text()`로 감싸야 함 (커밋 `5876a44` 수정됨)

**해결:** 이미 수정됨. DB 쿼리 시 `from sqlalchemy import text` 후 `text("SQL 문")` 사용.

---

## 2. 자주 발생하는 오류

### 2.1 서버 시작 실패

**증상:**
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**원인 & 해결:**

| 원인 | 확인 방법 | 해결 |
|------|----------|------|
| Ingestion 서버 미실행 | `curl http://localhost:8001/health` | `python mock_ingestion_server.py` 실행 |
| 포트 충돌 | `lsof -i :8080` | `PORT=8081`로 변경 |
| PostgreSQL 미실행 | `pg_isready -h localhost` | DB 실행 또는 `USE_MOCK_DB=true` |

---

### 2.2 챗봇을 찾을 수 없음 (404)

**증상:**
```json
{"detail": "Chatbot not found or inactive"}
```

**원인 & 해결:**
1. `chatbots/` 디렉토리에 해당 JSON 파일이 없음 → 파일 생성
2. JSON의 `"active": false` → `true`로 변경
3. JSON 파일이 있지만 서버가 인식 못함 → `POST /admin/api/chatbots/reload` 호출

---

### 2.3 권한 오류 (403)

**증상:**
```json
{"detail": "Access denied"}
```

**원인 & 해결:**
1. `USE_MOCK_AUTH=true` 시: `USE_MOCK_DB=true`이면 기본적으로 user-001에게 모든 권한 부여됨. DB에 권한이 없다면 `POST /api/permissions/`로 추가.
2. `USE_MOCK_AUTH=false` 시: SSO로 인식된 `knox_id`가 해당 챗봇 권한이 없음 → DB에서 권한 추가.

```bash
# 권한 추가 (curl)
curl -X POST http://localhost:8080/api/permissions/ \
  -H "Content-Type: application/json" \
  -d '{"knox_id": "your-knox-id", "chatbot_id": "chatbot-hr", "can_access": true}'
```

---

### 2.4 LLM 응답 없음 / 타임아웃

**증상:** SSE 스트림이 열리지만 데이터 없이 종료

**원인 & 해결:**
1. LLM 서버 미실행 → `LLM_BASE_URL` 서버 확인
2. 모델 이름 오류 → `LLM_DEFAULT_MODEL` 또는 챗봇 JSON의 `model` 필드 확인
3. 타임아웃 → `LLM_TIMEOUT` 값 증가 (기본: 120초)
4. API 키 오류 → `LLM_API_KEY` 확인

---

### 2.5 RAG 검색 결과 없음

**증상:** 답변이 검색 컨텍스트 없이 생성됨 (신뢰도 낮음)

**원인 & 해결:**
1. Ingestion 서버 미실행 → `curl http://localhost:8001/health`
2. 챗봇의 `db_ids`가 Ingestion 서버에 없는 인덱스 → 인덱스 확인
3. 검색 쿼리와 문서 간 유사도 낮음 → Mock 서버 사용 시 키워드 확인

---

### 2.6 위임이 예상대로 동작하지 않음

**증상:** 신뢰도가 낮은데도 하위 챗봇으로 위임하지 않음

**진단:**

```bash
# 상세 로그 활성화 (DEBUG=true)
DEBUG=true python app.py

# 로그에서 위임 관련 항목 확인
# "[Delegation] confidence=X threshold=Y"
# "[HierarchicalExecutor] delegating to child: ..."
```

**확인 사항:**
1. `policy.delegation_threshold` 값 확인 (기본: 70)
2. `sub_chatbots` 배열이 올바르게 설정되어 있는지 확인
3. `policy.hybrid_score_threshold` 값이 너무 높지 않은지 확인 (기본: 0.15)

---

### 2.7 SSO 로그인 루프

**증상:** 로그인 후 계속 `/sso`로 리다이렉트됨

**원인 & 해결:**
1. `SECRET_KEY` 미설정 → `.env`에 설정
2. 세션 쿠키 만료 → 브라우저 쿠키 삭제 후 재시도
3. `SSO_REDIRECT_URI`가 실제 서버 주소와 다름 → SSO 설정 확인

---

### 2.8 JSON 파싱 오류 (챗봇 로드 실패)

**증상:**
```
json.JSONDecodeError: Expecting value: line X column Y
```

**원인 & 해결:**
1. `chatbots/*.json` 파일 문법 오류 → JSON 유효성 검사

```bash
# JSON 유효성 검사
python -m json.tool chatbots/chatbot-new.json
```

---

## 3. 디버깅 가이드

### 3.1 헬스체크

```bash
curl http://localhost:8080/health
```

예상 응답:
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

### 3.2 챗봇 목록 확인

```bash
curl http://localhost:8080/admin/api/chatbots | python -m json.tool
```

---

### 3.3 Ingestion 서버 직접 테스트

```bash
curl -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -H "x-api-key: secret-key" \
  -d '{
    "query": "연차 신청",
    "index_names": ["db_hr_overview"],
    "top_k": 3
  }'
```

---

### 3.4 로그 레벨 설정

```bash
# 디버그 모드 (SQL 쿼리 + 파일 변경 감지)
DEBUG=true python app.py

# uvicorn 로그 레벨
uvicorn app:app --log-level debug
```

---

## 4. FAQ

**Q: 새 챗봇을 추가했는데 API에서 보이지 않습니다.**

A: `POST /admin/api/chatbots/reload`를 호출하거나 서버를 재시작하세요. 서버는 시작 시 `chatbots/` 디렉토리를 스캔합니다.

---

**Q: `USE_MOCK_DB=true`인데 대화 기록이 서버 재시작 후 사라집니다.**

A: Mock DB는 인메모리이므로 재시작 시 초기화됩니다. 영속성이 필요하면 `USE_MOCK_DB=false` + PostgreSQL을 사용하세요.

---

**Q: 챗봇이 한국어로 답변하지 않습니다.**

A: 챗봇 JSON의 `system_prompt`에 한국어 답변 지시를 추가하세요:
```json
"system_prompt": "당신은 한국어로 답변하는 어시스턴트입니다."
```

---

**Q: 계층 깊이는 최대 몇 단계까지 지원하나요?**

A: `ChatbotManager`의 `MAX_HIERARCHY_DEPTH = 5`로 제한되어 있습니다. 실제 운영에서는 3단계(Root → Parent → Child)까지 검증되었습니다.

---

**Q: SSO 없이 여러 사용자를 테스트하려면?**

A: `USE_MOCK_AUTH=true` 상태에서 `backend/auth/mock_auth.py`의 `knox_id`를 변경하거나, 직접 권한 API를 호출해 다양한 권한 시나리오를 테스트할 수 있습니다.

---

**Q: Ingestion 서버 없이 LLM만 테스트할 수 있나요?**

A: 가능합니다. `mock_ingestion_server.py`를 실행하면 실제 벡터 DB 없이도 샘플 문서로 테스트할 수 있습니다. 또는 챗봇의 `db_ids`를 빈 배열로 설정하면 RAG 없이 LLM만 호출됩니다.

---

## 5. 환경별 체크리스트

### 로컬 개발

- [ ] Python 가상환경 활성화
- [ ] `mock_ingestion_server.py` 실행 (포트 8001)
- [ ] `.env` 파일의 `LLM_BASE_URL` 유효한 LLM 서버 주소
- [ ] `USE_MOCK_DB=true`, `USE_MOCK_AUTH=true`

### 스테이징/프로덕션

- [ ] PostgreSQL 실행 및 스키마 생성
- [ ] 실제 Ingestion 서버 실행
- [ ] 실제 LLM 서버 주소 설정
- [ ] SSO 설정 (필요 시)
- [ ] `SECRET_KEY` 강력한 값으로 설정
- [ ] `DEBUG=false`
