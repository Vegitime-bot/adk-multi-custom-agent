# 2026-04-08 DB 권한 및 접근 제어 개선

## 개요
사내서버(`use_mock_auth=true`) 환경에서 DB 권한이 없는 사용자가 챗봇에 접근할 때, "권한이 없습니다" 대신 "조회를 못했습니다"라는 부정확한 에러 메시지가 표시되던 문제를 해결함.

## 문제 상황
- **증상**: 권한 없는 DB 조회 시 "관련 문서를 찾지 못했습니다" 메시지 출력
- **원인**: 
  1. `get_user_db_scope()`가 `USE_MOCK_AUTH=true`일 때 모든 DB를 허용하던 하드코딩
  2. 권한 체크와 DB 쿼리 에러가 구분되지 않아 동일한 메시지로 처리됨

## 변경 사항

### 1. backend/api/chat.py

#### 사용자별 DB 스코프 분리 (`MOCK_USER_DB_SCOPE`)
```python
MOCK_USER_DB_SCOPE = {
    "user-001": {"db_001", "db_002", "db_003", "db_004", "db_005"},  # 관리자
    "user-002": {"db_001"},  # 인사팀
    "user-003": {"db_002", "db_003"},  # 기술팀
    "guest": {"db_001"},
    "jyd1234": {"db_001", "db_002", "db_003", "db_004", "db_005"},
    "yd86.jang": {"db_001", "db_002", "db_003", "db_004", "db_005", "snp"},  # 실제 사용자 추가
}
```

#### 챗봇 단위 DB 접근 권한 구현
- **챗봇 접근 권한**이 있으면 해당 챗봇이 사용하는 **모든 DB 자동 허용**
- `USE_MOCK_AUTH=true`: Mock 데이터 기반 권한 체크
- `USE_MOCK_AUTH=false`: `user_chatbot_access` 테이블 기반 권한 체크 (SSO 연동)

#### 권한 에러 메시지 개선
- 권한 없을 때 HTTP 403 에러 반환
- 명확한 메시지: `"해당 챗봇에 접근할 수 있는 데이터베이스 권한이 없습니다. 요청: {...}, 허용: {...}"`

#### 로깅 강화
```
[DB Scope] 사용자 {knox_id}의 접근 가능 DB: {...}
[Chat {id}] 사용자 {knox_id}의 DB 접근 권한 없음: {missing_dbs}
[Chat {id}] 사용자 {knox_id}의 제한된 DB 접근 - 허용: {...}, 거부: {...}
```

### 2. backend/retrieval/ingestion_client.py
- HTTP 403 Forbidden 에러 구분 및 상세 로깅 추가
- 기타 예외도 `type(e).__name__`으로 명확히 표시

## 동작 방식 변경

### 이전 동작
```
모든 사용자 → 모든 DB 접근 가능 → 권한 없으면 "조회 실패" 메시지
```

### 변경 후 동작
```
사용자 인증 → 챗봇 권한 확인 → (있으면) 해당 챗봇의 DB 모두 허용
                                   → (없으면) HTTP 403 "권한 없음"
```

## 테스트 결과
- **통과**: 60개
- **에러**: 3개 (conftest.py fixture 의존성 - 별도 스크립트 파일)
- **주요 테스트**: 위임 로직, 웹 페이지, 계층 구조 등 정상 동작 확인

## 커밋 이력
1. `feat: 사용자별 DB 스코프 분리 및 권한 에러 개선` - 초기 구현
2. `fix: yd86.jang 사용자 DB 권한 추가` - 실제 사용자 권한 추가
3. `fix: 챗봇 단위 DB 접근 권한 구현 및 중복 체크 제거` - 로직 정리 및 최종 정리

## 다음 LLM을 위한 참고사항
- **Mock vs 운영**: `USE_MOCK_AUTH` 설정에 따라 권한 체크 경로가 달라짐
- **DB 권한 테이블**: 현재는 `user_chatbot_access` 테이블로 챗봇 단위 관리. 향후 DB별 세분화가 필요하면 별도 테이블 추가 필요
- **테스트 파일**: `comprehensive_test.py`, `test_delegation_flow.py`는 pytest fixture 없이 직접 실행하는 스크립트임
- **로그 확인**: `[DB Scope]`, `[Chat {}] authorized_db_ids` 로그로 권한 문제 디버깅 가능
