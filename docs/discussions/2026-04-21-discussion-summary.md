# 2026-04-21 논의 내용 정리

## 참여자
- youngdong jang (8776598594)

## 주요 논의 주제

### 1. 계층적 위임 ON/OFF 모드 불일치 문제

**문제:**
- OFF 모드 (`multi_sub_execution: false`): 가장 적합한 1개만 실행 (의도된 동작 ✅)
- ON 모드 (`multi_sub_execution: true`): threshold 필터링 없이 모든 하위 챗봘 실행
- 결과: "PDDI 52주차 주간보고" vs "PDDI W52 Weekly report" 질문에 따라 답변 성공/실패가 달라짐

**원인:**
- ON 모드에서는 `hybrid_score_threshold` 필터링이 적용되지 않음
- 챗봇 선택은 정확히 되지만, RAG 검색 시 표현 차이(한글/영어)로 인해 실패

---

### 2. 히스토리 관리 문제 (핵심 이슈)

**문제:**
- "A회의록 검색해줘" → "이 리스크 헤지에 대해 자세히 설명해"
- 사용자 의도: A회의록 내 리스크 헤지 질문
- 실제 동작: 전체 DB에서 리스크 헤지 검색 (컨텍스트 손실)

**현재 구현 상태:**

| 기능 | 상태 | 설명 |
|------|------|------|
| 히스토리 저장 | ✅ 있음 | `MemoryManager`로 (chatbot_id, session_id)별 저장 |
| 히스토리 LLM 전달 | ✅ 있음 | `_build_messages_with_history`로 프롬프트에 포함 |
| 히스토리 기반 RAG 검색 | ❌ 없음 | "이 리스크 헤지"가 "A회의록 리스크 헤지"로 확장 안 됨 |
| 검색 결과 DB 저장 | ❌ 없음 | retrieve된 문서 추적 안 됨 |
| 히스토리 압축/요약 | ❌ 없음 | 대화 맥락을 검색 쿼리에 반영 안 됨 |

---

### 3. Google ADK 이식 검토

**ADK 제공 기능:**
- `SessionService`: 세션/히스토리 관리
- `MemoryService`: 장기 메모리/검색
- `State`: 세션별 임시 데이터
- 멀티 에이전트 오케스트레이션

**이식 가능성:**
- 가능하지만 상당한 리팩토링 필요
- 현재 계층적 위임 로직, 멀티 테넌트 구조, RAG 연동 등 전면 재작성

**결론:**
- 당장은 현재 구조에서 히스토리 기능 확장
- 추후 ADK 마이그레이션은 별도 프로젝트로 검토

---

### 4. Context Compaction 방식 결정

**주요 LLM 서비스 방식:**
- ChatGPT/Claude: Sliding Window + Summarization
- Gemini: 긴 컨텍스트 그대로 유지

**결정사항:**
- **LLM 기반 히스토리 압축(compaction)** 방식 채택
- 히스토리를 요약하여 검색 쿼리에 포함

**구현 계획:**
```python
# 1. 히스토리 압축 (LLM 호출)
def _compact_history(self, history: list[Message]) -> str:
    # 입력: [A회의록 검색 → 답변, 리스크 헤지 설명 요청]
    # 출력: "A회의록에서 리스크 헤지 관련 내용을 찾아본 상태"

# 2. 검색 쿼리 확장
def _build_contextual_query(self, compacted: str, message: str) -> str:
    # 출력: "A회의록 리스크 헤지에 대해 자세히 설명해"
```

**적용 대상:**
- `AgentExecutor.execute()`
- `HierarchicalAgentExecutor` (위임 시에도 히스토리 유지)

---

## 다음 작업

1. **히스토리 압축 기능 구현** (`AgentExecutor`, `HierarchicalAgentExecutor`)
2. **ON 모드 threshold 필터링 적용** 검토
3. **테스트 케이스 작성**
   - "A회의록 검색 → 리스크 헤지 상세 설명" 흐름 테스트

---

*작성일: 2026-04-21*
