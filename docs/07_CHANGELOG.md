# 07. 변경 이력 (Changelog)

> Git 커밋 히스토리 기반 (`git log --oneline --all`)

---

## 2026-04-07 (최신)

### 변경사항

| 커밋 | 타입 | 설명 |
|------|------|------|
| `e737d97` | chore | CORS 미들웨어 제거 (불필요) |
| `bd7e43c` | feat | 루트 경로를 `/admin`으로 변경, 챗봘→챗봇 오타 수정 |
| `ede75cc` | fix | `permissions`: `updated_at` 컬럼 제거 (ORM-DB 불일치 수정) |
| `2be0ff7` | feat | `chat`: PermissionRepository 연동하여 DB 기반 권한 조회 |
| `1cbf991` | fix | `chat`: SSO knox_id 관계없이 모든 사용자 권한 부여 (임시 패치) |

---

## 2026-04 (SSO 통합 & DB 연동)

| 커밋 | 타입 | 설명 |
|------|------|------|
| `fafb17d` | refactor | SSO 단순화 - `sso.py`에 위임, `app.py`는 세션만 체크 |
| `6619182` | feat | `/acs` POST 핸들러 추가 (IdP SSO 콜백 처리) |
| `a3dc4b9` | fix | PostgreSQL DB 연결 및 세션 관리 개선 |
| `e0d79f8` | fix | `auth`: knox_id 없어도 SSO 인증된 것으로 처리 |
| `937b832` | fix | SSO 쿠키 설정 및 디버깅 로그 개선 |
| `b4a107f` | chore | SSO 디버깅 로그 추가 (토큰 파싱, 세션 확인) |
| `d3b7341` | fix | `app`: IdP POST 콜백에서 `id_token` 파싱 및 `knox_id` 세션 저장 |
| `98a352e` | fix | `auth`: 세션 기반 SSO 인증 추가 |
| `2a383e1` | fix | `app`: `SessionMiddleware` 추가 (SSO 세션 지원) |
| `4c7aa37` | fix | `app`: SSO POST 콜백 처리 추가 |
| `bc6ccee` | fix | `app`: SSO 인증 체크 로직 수정 - 세션 기반 리다이렉트 |
| `a3792b9` | fix | 중복 루트 엔드포인트 제거, SSO 콜백 후 리다이렉트 추가 |
| `c3ff55b` | fix | SSO 리다이렉트 시 쿼리 파라미터 보존, 루트 엔드포인트 인증 체크 추가 |
| `397ca58` | refactor | `SessionMiddleware` 제거, SSO 내부 템플릿 방식으로 변경 |
| `5ebaeb8` | refactor | SSO를 내부 템플릿 포맷으로 재구성 |
| `5876a44` | fix | SQLAlchemy 2.0 호환성: SQL을 `text()`로 감싸기 |
| `78a07a1` | docs | README에 SSO 설정 가이드 업데이트 |
| `09f3aef` | refactor | SSO 통합을 위한 앱 구조 재구성 |

---

## 2026-03 (인증 & Ingestion 개선)

| 커밋 | 타입 | 설명 |
|------|------|------|
| `466571b` | fix | API 키 헤더 변경: `API_KEY` → `x-api-key` |
| `58ebb10` | docs | `INGESTION_API_KEY`, `LLM_DEFAULT_*` 환경변수 `.env.example`에 추가 |
| `c846f06` | fix | '복지', '인사' 쿼리 키워드 매칭 개선 |
| `ff147d4` | feat | Mock Ingestion 서버에 API_KEY 인증 추가 |
| `7be8731` | feat | Ingestion 서버 인증을 위한 `INGESTION_API_KEY` 추가 |
| `a462ab6` | fix | `USE_MOCK_AUTH=true` 시 모든 모드 허용 |
| `ee95a5d` | fix | `USE_MOCK_AUTH=true` 시 모든 챗봇 접근 허용 |
| `68941a8` | fix | LLM 스트리밍 `choices` 빈 리스트 에러 처리 |
| `76fd0ad` | feat | 위임 디버깅을 위한 상세 로그 추가 |

---

## Stage 3/4: 계층적 위임 & 고급 기능

| 커밋 | 타입 | 설명 |
|------|------|------|
| `76fd0ad` | feat | Multi Custom Agent Service Stage 3/4 구현 완료 |
| `0b98081` | feat | 대화 기록 API, 임베딩 기반 하이브리드 위임, 관리자 삭제 후 리로드 수정 |
| `b479165` | feat | 관리자 패널: 계층 뷰, 사용자 권한, 통계 대시보드 추가 |
| `9530248` | feat | URL 파라미터 기반 챗봇 자동 선택, 웹 E2E 테스트 추가 |
| `79e9e3d` | feat | App Store 스타일 챗봇 관리 관리자 패널 추가 |
| `5683ae0` | feat | 향상된 DB와 위임 테스트 추가 |
| `eb8a6eb` | feat | 도메인별 Mock DB 데이터 추가 (HR, Tech, RTL) |
| `6dd1010` | fix | chatbot-c RTL 접근 권한 수정 |
| `d9bfaf1` | feat | 신뢰도 기반 위임 로직이 포함된 상위 에이전트 개선 |
| `765a8de` | feat | 부모-자식 에이전트 계층 및 위임 로직 추가 |

---

## Phase 1~4: Executor 기반 아키텍처

| 커밋 | 타입 | 설명 |
|------|------|------|
| `0225634` | feat | Phase 1~4 완료: Executor 기반 아키텍처 개선 |
| `418e325` | feat | 새 챗봇 및 기본 Executor 추가 |
| `1a92a49` | feat | `LLMConfig`에서 model을 선택적으로 지원 |
| `8ef2c4f` | fix | 기본 모델 변경: `gpt-4o` → `GLM4.7` |
| `e2fc751` | feat | Chat API에 상세 디버그 로그 추가 |

---

## 초기 개발

| 커밋 | 타입 | 설명 |
|------|------|------|
| `c812b00` | add | LLM 연결 테스트 스크립트 추가 |
| `81224df` | fix | `.env` 파일 자동 로드 지원 |
| `afa5b43` | docs | README에 Mock Ingestion 서버 실행 단계 추가 |
| `fcdc9de` | fix | BASE URL 동적 설정, README 추가 |
| `7c0e9ff` | fix | PORT 8080, `/api/chatbots` 버그 수정 |
| `52fe0af` | init | 초기 커밋: Multi Custom Agent Service |

---

## 주요 기능 추가 타임라인

```
2026-04-07  ─── CORS 제거, 루트→/admin 리다이렉트, DB 권한 연동
2026-04     ─── SSO OIDC 통합, PostgreSQL 연동
2026-03     ─── Ingestion API 키 인증, 키워드 매칭 개선
─────────── ─── Stage 3/4: 대화 기록 API, 임베딩 기반 하이브리드 위임
─────────── ─── 관리자 패널: 계층 뷰, 권한 관리, 통계 대시보드
─────────── ─── 부모-자식 에이전트 계층 및 신뢰도 기반 위임
─────────── ─── Phase 1~4: Executor 기반 아키텍처 (Tool/Agent/Hierarchical)
─────────── ─── 초기: FastAPI 서버, 챗봇 JSON 정의, RAG 검색 연동
```

---

## 삭제된 기능/파일

| 항목 | 커밋 | 사유 |
|------|------|------|
| CORS 미들웨어 | `e737d97` | 불필요 (내부망 서비스) |
| `updated_at` 컬럼 (권한 테이블) | `ede75cc` | ORM-DB 불일치 수정 |
| `SessionMiddleware` (1차 제거) | `397ca58` | SSO 구조 변경 |
| `parent_agent_executor.py` (실질적) | Phase 리팩토링 | `HierarchicalAgentExecutor`로 대체 |
| 9개 테스트 파일 | 현재 미반영 | 개발 중 정리 (현재 git status에 D로 표시) |
