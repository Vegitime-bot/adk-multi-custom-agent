# 개선 TODO 목록

> 우선순위: **P0** = LLM 교체 전 필수 / **P1** = 권장 / **P2** = 선택

---

## 1. LLM 응답 플로우 개선 `P0`

> LLM 모델 교체 전 반드시 해결해야 할 항목

### 현재 문제점

- **불명확한 위임 기준**: Confidence 70% 임계값이 코드에 하드코딩되어 있어 조정 불가
- **복잡한 위임 체인**: 하위 에이전트 실패 → 상위 에이전트 재시도 → ... 구조로 흐름 파악 어려움
- **일관성 없는 응답 형식**: 에이전트마다 응답 구조가 달라 파싱/후처리 불안정
- **메모리 관리 문제**: 위임 발생 시 대화 맥락(session context)이 끊겨 연속성 손실

### 개선 방안

- [ ] Confidence threshold를 설정 파일 또는 환경변수에서 조정 가능하도록 외부화
- [ ] 위임 로직 단순화: `_select_delegate_target()` 메서드를 별도로 분리하여 단일 책임화
- [ ] 표준 응답 포맷 도입: `{ answer, source, metadata }` 구조로 통일
- [ ] 위임 시에도 동일 `session_id` 유지 및 누적 컨텍스트 전달 보장

---

## 2. HierarchicalAgentExecutor 리팩토링 `P1`

### 현재 상태

`execute()` 메서드가 다음을 모두 처리:
- 검색 (Retrieval)
- Confidence 계산
- 하위 에이전트 위임
- 상위 에이전트 위임
- Fallback 처리

### 개선 방안

- [ ] 단일 책임 원칙(SRP) 적용
  - `execute()` → "위임 결정"만 담당
  - 실제 실행 로직은 별도 메서드(`_run_local()`, `_run_delegate()`)로 분리
- [ ] Generator 패턴 대신 `Result` 객체 패턴 도입 검토 (명시적 성공/실패 표현)
- [ ] 상태 머신 패턴 도입 검토: `AgentState` (IDLE → SEARCHING → DELEGATING → DONE)

---

## 3. 디버깅 및 테스트 개선 `P1`

- [ ] 프로덕션 코드의 `print()` / `INFO` 로그를 `DEBUG` 레벨로 제한
- [ ] 위임 경로 추적 기능 추가: 어떤 에이전트가 어느 순서로 호출되었는지 로그/메타데이터에 기록
- [ ] 단위 테스트 가능한 구조로 변경
  - 의존성 주입(DI) 패턴 적용으로 mock 용이하게
  - `execute()` 내부 로직을 순수 함수로 분리

---

## 4. 설정 개선 `P2`

- [ ] `HYBRID_SCORE_THRESHOLD` 외에 추가 파라미터 환경변수화
  - `MAX_DELEGATION_DEPTH`
  - `FALLBACK_ENABLED`
  - `RESPONSE_TIMEOUT_SECONDS`
- [ ] 위임 전략을 설정으로 선택 가능하도록
  - `delegation_strategy: "bottom_up"` (하위 우선, 현재 방식)
  - `delegation_strategy: "top_down"` (상위 우선)
  - `delegation_strategy: "parallel"` (병렬 위임 후 최고 신뢰도 선택)
