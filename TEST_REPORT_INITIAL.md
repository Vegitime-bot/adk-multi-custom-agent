# ADK 계층적 챗봇 검증 보고서

**검증 일시**: 2026-04-27 19:46 KST  
**검증 환경**: 로컬 (Ollama) / 사내 서버 대기 중  
**테스트 실행**: `test_hierarchy.py` (자동화 스크립트 작성 완료)

---

## 검증 계획 (TEST_PLAN.md)

| TC | 테스트명 | 목적 | 검증 방법 |
|----|---------|------|----------|
| TC1 | L0 직접 응답 | Confidence >= 70% 시 직접 답변 | `/api/chat` 호출 → Confidence 확인 |
| TC2 | L0 → L1 위임 | Confidence < 70% 시 L1로 위임 | 위임 대상 확인 |
| TC3 | L1 → L2 위임 | 연쇄 위임 동작 | 위임 체인 확인 |
| TC4 | 상향 위임 | enable_parent_delegation | L2 거절 → 상위 컨텍스트 전달 |
| TC5 | 병렬 위임 | multi_sub_execution | 병렬 실행 및 응답 합성 |
| TC6 | SSE 스트리밍 | 실시간 응답 | SSE 형식 확인 |

---

## 구현 상태

### ✅ 완료된 항목

| 파일 | 상태 | 설명 |
|------|------|------|
| `adk_agents/tools/delegation_tools.py` | ✅ | 신뢰도 계산, 하위 챗봇 선택 |
| `adk_agents/sub_agent_factory.py` | ✅ | JSON → ADK Agent 변환 |
| `adk_agents/delegation_router_agent/__init__.py` | ✅ | 중앙 라우터 |
| `backend/api/chat_service_v2.py` | ✅ | 통합 서비스 |
| `backend/api/chat.py` | ✅ | V1/V2 전환 |
| `test_hierarchy.py` | ✅ | TC1-TC6 자동화 테스트 |

### 구현된 기능

1. **신뢰도 계산** (`calculate_confidence`)
   - RAG 결과 수 기반: 40점 (최대)
   - 평균 유사도 기반: 60점 (최대)
   - 0-100 범위 정규화

2. **위임 결정** (`DelegationContext`)
   - 임계값: 70% (기본)
   - 하이브리드 스코어링: 키워드 + 임베딩

3. **계층 구조**
   ```
   chatbot-company (L0)
     ├── chatbot-hr (L1) [sub_agent]
     │   ├── chatbot-hr-policy (L2)
     │   └── chatbot-hr-benefit (L2)
     └── chatbot-tech (L1) [sub_agent]
         ├── chatbot-tech-backend (L2)
         └── chatbot-tech-frontend (L2)
   ```

---

## 테스트 실행 방법

### 1. 로컬 테스트 (Ollama)

```bash
# 환경 설정
export DEVELOPMENT=true
export USE_CHAT_SERVICE_V2=true
export OLLAMA_MODEL=kimi-k2.5:cloud
export OLLAMA_BASE_URL=http://localhost:11434/v1

# 서버 실행
python app.py

# 테스트 실행 (새 터미널)
python test_hierarchy.py http://localhost:8080
```

### 2. 사내 서버 테스트

```bash
# 사내 서버에서
export USE_CHAT_SERVICE_V2=true
export DEVELOPMENT=false
export LLM_DEFAULT_MODEL=GLM4.7
export LLM_BASE_URL=http://llm-gw.company.com:8000/v1
export LLM_API_KEY=your-api-key

python app.py

# 테스트 실행 (로컬 또는 다른 머신)
python test_hierarchy.py http://<server-ip>:8080
```

---

## 예상 결과 및 체크리스트

### 성공 기준
- [ ] TC1: Confidence >= 70% 시 L0 직접 답변
- [ ] TC2: Confidence < 70% 시 L1로 위임
- [ ] TC3: L1 → L2 연쇄 위임
- [ ] TC4: L2 거절 시 상위로 컨텍스트 전달
- [ ] TC5: 다중 하위 챗봇 병렬 실행
- [ ] TC6: SSE 스트리밍 응답

### 실패 시 대응

| 증상 | 원인 | 조치 |
|------|------|------|
| `USE_CHAT_SERVICE_V2` 미설정 | V1로 동작 | 환경변수 설정 |
| Confidence 미표시 | 프롬프트 미적용 | `sub_agent_factory.py` 확인 |
| 위임 없음 | sub_agents 미로드 | JSON 정의 확인 |
| SSE 오류 | Runner 설정 | `DelegationRouter` 확인 |

---

## 다음 단계

1. **사내 서버 배포** 후 테스트 실행
2. **TC1-TC6 결과 분석**
3. **버그 수정** (발견 시)
4. **성능 벤치마크** (병렬 위임, 대기 시간)

---

**테스트 준비 완료: `test_hierarchy.py` 실행 대기 중**
