# ADK 계층적 챗봇 구조 개발 계획

## 목표
JSON 기반 챗봇 계층 구조를 ADK와 통합하여 구현
- Parent 챗봇이 신뢰도 기반으로 Child 챗봇에 위임
- JSON 정의(chatbots/*.json)를 ADK Agent로 동적 변환

## 현재 구조
```
chatbots/*.json ──→ ChatbotManager ──→ HierarchicalAgentExecutor(구형)
```

## 목표 구조
```
chatbots/*.json ──→ DelegationRouterAgent(ADK) ──→ sub_agents 동적 로드
                              ↓
                    ┌─────────┴─────────┐
              직접 응답          하위 Agent 위임
```

## Phase 1: Architecture (설계)
### 요구사항 분석
1. JSON 스키마 파싱 및 검증
2. 신뢰도 계산 로직 (RAG 결과 기반)
3. 위임 결정 엔진
4. Parent-Child 관계 매핑
5. ADK Agent 동적 생성

### 아키텍처 컴포넌트
```
┌─────────────────────────────────────────────────────────┐
│              DelegationRouterAgent (ADK)                │
│  - JSON 정의 로드 (chatbot_manager 연동)                 │
│  - RAG 결과 기반 신뢰도 계산                             │
│  - 위임/직접응답 결정                                   │
│  - sub_agents 동적 구성                                 │
├─────────────────────────────────────────────────────────┤
│  sub_agents: 동적 로드된 Child Agents                   │
│  - chatbot-hr → chatbot-hr-policy                       │
│  - chatbot-hr → chatbot-hr-benefit                      │
└─────────────────────────────────────────────────────────┘
```

### 데이터 모델
- ChatbotDef (기존) + ADK Agent 매핑
- DelegationContext: 신뢰도, 추천 하위 챗봇, 위임 사유

### API 설계
- `/api/chat` → DelegationRouterAgent 호출
- 내부: Router → (직접 | sub_agent)

## Phase 2: Implementation (구현)
### 구현 순서
1. **adk_agents/delegation_router_agent/__init__.py**
   - JSON 기반 Router Agent 생성
   - tools: calculate_confidence, select_sub_chatbot

2. **adk_agents/sub_agent_factory.py**
   - JSON → ADK Agent 변환 팩토리
   - sub_agents 동적 로드

3. **backend/api/chat_service_v2.py**
   - Router Agent 기반 채팅 서비스
   - 기존 chat_service 대체/업그레이드

4. **adk_agents/tools/delegation_tools.py**
   - RAG 검색 → 신뢰도 계산
   - 하이브리드 스코어링 (keywords + embedding)

## Phase 3: Validation (검증)
### 테스트 시나리오
1. L0 → 직접 응답 (신뢰도 70% 이상)
2. L0 → L1 위임 (신뢰도 70% 미만)
3. L1 → L2 위임 (연쇄 위임)
4. 상향 위임 (L2 → L1 → L0)
5. 병렬 위임 (multi_sub_execution)

### 검증 항목
- JSON 정의와 ADK Agent 일치성
- 신뢰도 계산 정확성
- 위임 체인 정상 동작
- SSE 스트리밍 유지

---

위 계획을 Architecture Agent에게 전달하여 상세 설계를 받겠습니다.
