# JSON 기반 계층 구조 ADK 통합 설계

## Phase 1: Architecture (설계 완료)

### 핵심 아키텍처
```
[JSON 정의] → [DelegationRouterAgent] → [sub_agents 동적 로드]
                (ADK Agent)              (ADK Agents)
```

### 주요 컴포넌트

| 컴포넌트 | 역할 | 파일 |
|---------|------|------|
| **ChatbotManager** | JSON 로드 및 계층 관리 | `backend/managers/chatbot_manager.py` |
| **SubAgentFactory** | JSON → ADK Agent 변환 | `adk_agents/sub_agent_factory.py` (신규) |
| **DelegationRouterAgent** | 위임 결정 및 라우팅 | `adk_agents/delegation_router_agent/__init__.py` (신규) |
| **DelegationTools** | 신뢰도 계산, 하위 선택 | `adk_agents/tools/delegation_tools.py` (신규) |
| **ChatServiceV2** | 통합 채팅 서비스 | `backend/api/chat_service_v2.py` (신규) |

### 데이터 흐름
```
1. 사용자 질문 → ChatServiceV2
2. ChatbotManager가 JSON 로드
3. SubAgentFactory가 Root Agent 생성
4. DelegationRouterAgent 실행
   - RAG 검색 → 신뢰도 계산
   - 70% 이상: 직접 응답
   - 70% 미만: sub_agents에서 선택 → 위임
5. SSE 스트리밍 응답
```

### JSON-ADK 매핑
```json
// JSON (chatbot-company.json)
{
  "id": "chatbot-company",
  "sub_chatbots": [
    {"id": "chatbot-hr", ...},
    {"id": "chatbot-tech", ...}
  ]
}

// ADK Agent
Agent(
  name="chatbot-company",
  sub_agents=[chatbot_hr_agent, chatbot_tech_agent],
  tools=[calculate_confidence, delegate_to_sub]
)
```

## Phase 2: Implementation (구현)

### 파일 생성 순서
1. `adk_agents/tools/delegation_tools.py` - 도구 정의
2. `adk_agents/sub_agent_factory.py` - Agent 변환 팩토리
3. `adk_agents/delegation_router_agent/__init__.py` - Router Agent
4. `backend/api/chat_service_v2.py` - 통합 서비스
5. `backend/api/chat.py` - Router 연동

### 구현 상세

#### 1. DelegationTools
```python
# RAG 검색 결과 기반 신뢰도 계산
@tool
def calculate_confidence(rag_results: list) -> float:
    """검색 결과 수와 평균 유사도로 신뢰도 계산"""
    if not rag_results:
        return 0.0
    count_score = min(len(rag_results) / 5, 1.0) * 40
    avg_score = sum(r.get('score', 0) for r in rag_results) / len(rag_results) * 60
    return count_score + avg_score

# 하위 챗봇 선택
@tool  
def select_sub_chatbot(query: str, sub_chatbots: list, keywords: dict) -> str:
    """키워드 + 임베딩 기반 하이브리드 스코어링"""
    # 구현...
```

#### 2. SubAgentFactory
```python
class SubAgentFactory:
    def create_agent(self, chatbot_def: ChatbotDef) -> Agent:
        sub_agents = [
            self.create_agent(sub) for sub in chatbot_def.sub_chatbots
        ]
        return Agent(
            name=chatbot_def.id,
            model=model,
            instruction=self._build_system_prompt(chatbot_def),
            sub_agents=sub_agents or None,
            tools=[calculate_confidence, select_sub_chatbot] if sub_agents else []
        )
```

#### 3. DelegationRouterAgent
```python
# 하위 챗봇이 있는 경우 위임 결정
agent = Agent(
    name="delegation_router",
    model=model,
    instruction="""
    당신은 챗봇 계층 구조의 Router입니다.
    
    처리 순서:
    1. calculate_confidence로 RAG 검색 결과 분석
    2. 신뢰도 >= 70%: 직접 응답 생성
    3. 신뢰도 < 70%: select_sub_chatbot으로 하위 챗봇 선택
    4. 선택된 하위 챗봇에 위임 (sub_agents 자동 호출)
    """,
    tools=[calculate_confidence, select_sub_chatbot]
)
```

#### 4. ChatServiceV2
```python
class ChatServiceV2:
    async def chat(self, chatbot_id: str, message: str, ...):
        # 1. JSON 로드
        chatbot = self.chatbot_manager.get_chatbot(chatbot_id)
        
        # 2. ADK Agent 생성 (캐싱)
        agent = self.agent_cache.get_or_create(chatbot_id, 
            lambda: self.sub_agent_factory.create_agent(chatbot))
        
        # 3. Runner 실행
        runner = Runner(agent=agent, ...)
        
        # 4. SSE 스트리밍
        async for event in runner.run_async(...):
            yield event.content
```

## Phase 3: Validation (검증)

### 테스트 케이스
| TC | 시나리오 | 기대 결과 |
|----|---------|----------|
| TC1 | L0 직접 응답 | chatbot-company가 직접 답변 |
| TC2 | L0 → L1 위임 | chatbot-company → chatbot-hr |
| TC3 | L1 → L2 위임 | chatbot-hr → chatbot-hr-policy |
| TC4 | 상향 위임 | L2 실패 시 L1로 컨텍스트 전달 |
| TC5 | 병렬 위임 | multi_sub_execution으로 동시 실행 |
| TC6 | SSE 유지 | 스트리밍 응답 정상 작동 |

### 검증 항목
- [ ] JSON 정의와 생성된 ADK Agent 일치
- [ ] 신뢰도 70% 기준으로 위임/직접응답 분기
- [ ] 위임 체인 정상 동작 (L0 → L1 → L2)
- [ ] 상향 위임 (enable_parent_delegation)
- [ ] SSE 스트리밍 유지
- [ ] 세션별 대화 히스토리 유지

---

**설계 완료 시간:** 2026-04-27 19:40 KST
**작성자:** Architecture/Implementation/Validation Agent 협업
