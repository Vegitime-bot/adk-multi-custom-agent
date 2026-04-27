# ADK 계층적 챗봇 검증 계획

## 검증 목표
JSON 기반 계층 구조 + ADK 통합이 정상 작동하는지 확인

## 테스트 환경
- **서버**: 사내 서버 또는 로컬 (Ollama 사용 시)
- **환경변수**: `USE_CHAT_SERVICE_V2=true`
- **명령**: `python app.py`

## 테스트 케이스 (TC1-TC6)

### TC1: L0 직접 응답
**목적**: 신뢰도 70% 이상 시 상위 챗봇이 직접 답변

**입력**:
```json
{
  "chatbot_id": "chatbot-company",
  "message": "회사 소개해줘"
}
```

**기대 결과**:
- Confidence: 75% 이상
- 응답에 "CONFIDENCE: XX" 포함
- chatbot-company가 직접 답변 (위임 없음)

**검증 방법**:
1. `/api/chat` 호출
2. 응답에서 "CONFIDENCE" 값 확인
3. 로그에서 위임 여부 확인

---

### TC2: L0 → L1 위임
**목적**: 신뢰도 70% 미만 시 L1로 위임

**입력**:
```json
{
  "chatbot_id": "chatbot-company",
  "message": "인사 정책 중 평가 제도 알려줘"
}
```

**기대 결과**:
- Confidence: 60% 미만
- 응답에 "DELEGATE_TO: chatbot-hr" 포함
- chatbot-hr이 답변

**검증 방법**:
1. `/api/chat` 호출
2. 응답에서 위임 대상 확인
3. 로그에서 sub_agent 호출 확인

---

### TC3: L1 → L2 위임 (연쇄 위임)
**목적**: L1에서도 신뢰도 낮으면 L2로 위임

**입력**:
```json
{
  "chatbot_id": "chatbot-hr",
  "message": "성과 평가 세부 기준 알려줘"
}
```

**기대 결과**:
- chatbot-hr confidence: 65% 미만
- chatbot-hr-policy로 위임
- L2 전문가가 상세 답변

**검증 방법**:
1. 위임 체인 확인 (L1 → L2)
2. 응답의 전문성 수준 확인

---

### TC4: 상향 위임 (enable_parent_delegation)
**목적**: 하위에서 해결 못하면 상위로

**입력**:
```json
{
  "chatbot_id": "chatbot-hr-policy",
  "message": "기술팀 연봉 협상 절차"
}
```

**기대 결과**:
- chatbot-hr-policy: "제 전문 분야가 아닙니다"
- 상위로 컨텍스트 전달
- chatbot-hr 또는 chatbot-company가 답변

**검증 방법**:
1. L2 응답 확인 (거절 메시지)
2. parent_id로 컨텍스트 전달 확인
3. 상위에서 재처리 확인

---

### TC5: 병렬 위임 (multi_sub_execution)
**목적**: 여러 하위 챗봇 동시 실행

**입력**:
```json
{
  "chatbot_id": "chatbot-company",
  "message": "인사와 기술 모두 관련된 문의"
}
```

**기대 결과**:
- chatbot-hr, chatbot-tech 병렬 실행
- 응답 합성

**검증 방법**:
1. 로그에서 병렬 실행 확인
2. 응답에 두 챗봘 정보 모두 포함

---

### TC6: SSE 스트리밍 유지
**목적**: 실시간 응답 스트리밍 정상 작동

**입력**: TC1-TC5 중 하나

**기대 결과**:
- `data: {...}\n\n` 형식의 SSE
- 실시간 청크 전송
- `done: true`로 종료

**검증 방법**:
1. 브라우저 DevTools Network 탭 확인
2. 응답 청크 간격 확인 (0.1-1초)
3. 전체 응답 완료 확인

---

## 테스트 실행 방법

### 1. 수동 테스트 (curl)
```bash
# TC1: 직접 응답
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"chatbot_id":"chatbot-company","message":"회사 소개"}'

# TC2: 위임
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"chatbot_id":"chatbot-company","message":"인사 정책"}'
```

### 2. 자동화 테스트 (Python)
```bash
python test_hierarchy.py
```

### 3. 웹 UI 테스트
1. 브라우저에서 `http://localhost:8080` 접속
2. 챗봇 선택 후 대화
3. 응답 확인

---

## 성공 기준
- TC1-TC6 모두 PASS
- Confidence 계산 정확성
- 위임 체인 정상 동작
- SSE 스트리밍 유지
- 세션별 히스토리 저장

## 실패 시 체크리스트
- [ ] `USE_CHAT_SERVICE_V2=true` 설정 확인
- [ ] chatbots/*.json 파일 존재 확인
- [ ] LLM 연결 확인 (Ollama 또는 사내 GW)
- [ ] 로그에서 에러 메시지 확인
