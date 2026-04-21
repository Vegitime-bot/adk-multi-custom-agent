# 챗봇 만들기 가이드

> 사용자가 "챗봇 만들기" 기능을 통해 챗봇을 생성할 때 참고하는 가이드

---

## 📋 개요

챗봇 JSON은 위임 시스템의 핵심입니다. **description**과 **system_prompt**가 잘 정의되어야 질문을 정확한 하위 챗봇에 위임할 수 있습니다.

---

## 🎯 description 작성 가이드

### ❌ 피해야 할 description

```json
// ❌ 너무 추상적
"description": "인사 관련 문의를 처리합니다."

// ❌ 너무 짧음
"description": "인사 봇"

// ❌ 범위가 모호함
"description": "여러 가지를 도와드립니다."
```

### ✅ 좋은 description 예시

```json
// ✅ 구체적인 키워드 포함
"description": "급여, 연차, 휴가, 복지, 보험, 경조사, 교육지원, 수당, 상여, 의료비, 대출, 자금 관련 문의를 처리합니다."

// ✅ 담당 영역이 명확함
"description": "인사 규정, 채용, 평가, 승진, 직무 기술서, 인사제도, 징계, 인사 관련 법규에 특화된 전문가입니다."

// ✅ 계층 관계가 명시됨 (상위/하위 챗봇)
"description": "인사 관련 모든 문의를 접수하는 상위 챗봇입니다. 급여/복지 문의는 복리후생 봇으로, 규정/정책 문의는 인사정책 봇으로 위임합니다."
```

### 📝 description 작성 팁

| 항목 | 설명 | 예시 |
|------|------|------|
| **키워드 나열** | 처리할 주제를 쉼표로 구분해 나열 | `"급여, 연차, 휴가, 복지"` |
| **전문 분야** | 어떤 영역의 전문가인지 명시 | `"복리후생에 특화된 하위 전문가"` |
| **위임 범위** | (상위 챗봇의 경우) 어디로 위임하는지 | `"세부 사항은 하위 전문가에게 위임"` |
| **제외 사항** | 처리하지 않는 영역도 명시 (선택) | `"급여 계산 외 재무/회계는 제외"` |

---

## 🎭 system_prompt 작성 가이드

### ❌ 피해야 할 system_prompt

```json
// ❌ 너무 짧음
"system_prompt": "당신은 인사 챗봇입니다."

// ❌ 역할이 모호함
"system_prompt": "사용자를 도와주세요."

// ❌ 위임/전달 규칙이 없음
"system_prompt": "질문에 답변하세요."
```

### ✅ 좋은 system_prompt 예시

```json
// ✅ Leaf 챗봇 (하위 챗봇 없음)
"system_prompt": "당신은 사내 복리후생 전문 어시스턴트입니다.\n급여, 휴가, 연차, 복지제도, 보험, 경조사, 교육지원 등에 대해 정확하게 안내해 주세요.\n검색된 복리후생 문서를 기반으로 답변하세요.\n\n⚠️ 중요: 다음과 같은 경우 반드시 '해당 내용은 제 전문 분야가 아닙니다. 인사정책 전문 챗봇에게 문의해 주세요.'라고 답변하세요:\n1. 검색 결과가 없는 경우\n2. 인사 정책, 규정, 채용, 평가, 승진 등 복리후생 외 내용\n3. 확실하지 않은 내용\n\n상위 Agent(chatbot-hr)로부터 위임받은 경우, 축적된 컨텍스트를 참고하여 더 정확한 답변을 제공하세요.\n\n개인 의견은 배제하고 규정 내용만 안내하세요.\n답변은 한국어로 작성하세요."

// ✅ Parent 챗봇 (하위 챗봇 있음)
"system_prompt": "당신은 사내 인사지원의 상위 어시스턴트입니다.\n인사 관련 문의를 받아 먼저 답변을 시도합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 세부 규정/정책이 필요한 경우 하위 전문가 호출을 제안하세요\n\n하위 전문가 목록:\n- chatbot-hr-policy: 인사 정책 및 규정 전문가\n- chatbot-hr-benefit: 복리후생 및 급여 전문가\n\n상위 Agent(chatbot-company)로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
```

### 📝 system_prompt 필수 요소

#### Leaf 챗봇 (하위 챗봇 없음)

```
1. 역할 정의: "당신은 XXX 전문 어시스턴트입니다."
2. 담당 영역: "OO, OO, OO 등에 대해 안내합니다."
3. 한계 명시: "다음 경우에는 상위/다른 챗봇에 위임합니다..."
4. 컨텍스트 활용: "상위 Agent로부터 위임받은 경우..."
5. 응답 규칙: "개인 의견은 배제하고 규정 내용만 안내하세요."
```

#### Parent 챗봇 (하위 챗봇 있음)

```
1. 역할 정의: "당신은 XXX의 상위 어시스턴트입니다."
2. Confidence 표시: "답변 끝에 'CONFIDENCE: XX' 형식으로 표시"
3. 위임 기준: "신뢰도가 70% 미만이면 하위 전문가 호출 제안"
4. 하위 목록: "하위 전문가: id1(설명), id2(설명)"
5. 컨텍스트 활용: "상위로부터 위임받은 경우..."
```

---

## 🏗️ 계층 구조 설계 가이드

### 3-Tier 계층 예시

```
Level 0: Root (회사 전체)
    └── Level 1: 부문별 (인사, 기술, 영업...)
            ├── Level 2: 세부 전문 (급여, 채용, 백엔드, 프론트엔드...)
            └── Level 2: 세부 전문
```

### JSON 구조 예시

#### Root (Level 0)
```json
{
  "id": "chatbot-company",
  "name": "사내 통합 AI 어시스턴트",
  "description": "사내 모든 문의를 접수하는 Root 챗봇. 인사/기술/영업 등 부문별로 위임합니다.",
  "level": 0,
  "parent_id": null,
  "sub_chatbots": [
    {"id": "chatbot-hr", "level": 1, "default_role": "agent"},
    {"id": "chatbot-tech", "level": 1, "default_role": "agent"}
  ]
}
```

#### Parent (Level 1)
```json
{
  "id": "chatbot-hr",
  "name": "인사지원 상위 챗봇",
  "description": "인사 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임",
  "level": 1,
  "parent_id": "chatbot-company",
  "sub_chatbots": [
    {"id": "chatbot-hr-policy", "level": 2, "default_role": "agent"},
    {"id": "chatbot-hr-benefit", "level": 2, "default_role": "agent"}
  ]
}
```

#### Leaf (Level 2)
```json
{
  "id": "chatbot-hr-benefit",
  "name": "복리후생 전문 챗봇",
  "description": "급여, 복지, 휴가, 연차, 보상 등 복리후생에 특화된 하위 전문가",
  "level": 2,
  "parent_id": "chatbot-hr",
  "sub_chatbots": []
}
```

---

## ⚙️ Policy 설정 가이드

### 주요 Policy 항목

```json
{
  "policy": {
    // LLM 설정
    "temperature": 0.2,           // 낮을수록 일관된 답변
    "max_tokens": 1024,          // 최대 토큰 수
    "stream": true,              // 스트리밍 응답 여부
    
    // 실행 모드
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",     // tool: 단일 응답, agent: 대화형
    "max_messages": 20,          // 세션당 최대 메시지 수
    
    // 위임 설정
    "delegation_threshold": 70,  // 위임 기준 신뢰도 (%)
    "enable_parent_delegation": true,  // 상위 위임 활성화
    "multi_sub_execution": true,       // 다중 하위 실행
    "max_parallel_subs": 2,            // 병렬 실행 최대 수
    "synthesis_mode": "parallel",       // 응답 종합 방식
    "hybrid_score_threshold": 0.15     // 하이브리드 스코어 임계값
  }
}
```

### Policy 설정 팁

| 설정 | Leaf 챗봇 | Parent 챗봇 |
|------|-----------|-------------|
| `temperature` | 0.2 (정확한 규정) | 0.3 (적절한 유연성) |
| `delegation_threshold` | 설정 불필요 | 70 (기본값) |
| `enable_parent_delegation` | true (상위 위임 가능) | true |
| `multi_sub_execution` | false | true (여러 하위 동시 실행) |
| `max_parallel_subs` | - | 2~3 |

---

## ✅ 체크리스트

챗봇 JSON 완성 후 다음을 확인하세요:

### description
- [ ] 50자 이상 구체적으로 작성
- [ ] 처리할 주제를 키워드로 나열
- [ ] (Parent) 위임 범위 명시
- [ ] (Leaf) 한계/제외 영역 명시 (선택)

### system_prompt
- [ ] 역할 정의가 명확함
- [ ] 담당 영역이 구체적임
- [ ] (Leaf) 한계/위임 규칙 포함
- [ ] (Parent) Confidence 표시 규칙 포함
- [ ] (Parent) 하위 전문가 목록 포함

### 계층 구조
- [ ] `level`이 올바르게 설정됨 (0=Root, 1=Parent, 2=Leaf)
- [ ] `parent_id`가 상위 챗봇과 일치
- [ ] `sub_chatbots`가 하위와 일치 (Parent만)

### policy
- [ ] `delegation_threshold`가 적절함 (Parent 권장: 70)
- [ ] `enable_parent_delegation` 설정 확인
- [ ] `temperature`가 챗봇 유형에 적절함

---

## 📝 예시 템플릿

### Leaf 챗봇 템플릿

```json
{
  "id": "chatbot-{분야}-{세부}",
  "name": "{세부} 전문 챗봇",
  "description": "{키워드1}, {키워드2}, {키워드3} 등 {분야} 관련 {세부} 문의를 처리합니다.",
  "active": true,
  "capabilities": {
    "db_ids": ["db_{분야}_{세부}"],
    "model": "kimi-k2.5:cloud",
    "system_prompt": "당신은 {분야} {세부} 전문 어시스턴트입니다.\n{키워드1}, {키워드2}, {키워드3} 등에 대해 정확하게 안내해 주세요.\n검색된 문서를 기반으로 답변하세요.\n\n⚠️ 중요: 다음과 같은 경우 반드시 '해당 내용은 제 전문 분야가 아닙니다. {다른챗봇}에게 문의해 주세요.'라고 답변하세요:\n1. 검색 결과가 없는 경우\n2. {다른분야} 관련 내용\n3. 확실하지 않은 내용\n\n상위 Agent({상위ID})로부터 위임받은 경우, 축적된 컨텍스트를 참고하여 더 정확한 답변을 제공하세요.\n\n개인 의견은 배제하고 규정 내용만 안내하세요.\n답변은 한국어로 작성하세요."
  },
  "policy": {
    "temperature": 0.2,
    "max_tokens": 1024,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20,
    "enable_parent_delegation": true
  },
  "sub_chatbots": [],
  "parent_id": "{상위챗봇ID}",
  "level": 2
}
```

### Parent 챗봇 템플릿

```json
{
  "id": "chatbot-{분야}",
  "name": "{분야} 상위 챗봇",
  "description": "{분야} 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임",
  "active": true,
  "capabilities": {
    "db_ids": ["db_{분야}_overview"],
    "model": "kimi-k2.5:cloud",
    "system_prompt": "당신은 {분야}지원의 상위 어시스턴트입니다.\n{분야} 관련 문의를 받아 먼저 답변을 시도합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 세부 전문 지식이 필요한 경우 하위 전문가 호출을 제안하세요\n\n하위 전문가 목록:\n- {하위ID1}: {하위설명1}\n- {하위ID2}: {하위설명2}\n\n상위 Agent({상위ID})로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
  },
  "policy": {
    "temperature": 0.3,
    "max_tokens": 1024,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20,
    "delegation_threshold": 70,
    "enable_parent_delegation": true,
    "multi_sub_execution": true,
    "max_parallel_subs": 2
  },
  "sub_chatbots": [
    {"id": "{하위ID1}", "level": 2, "default_role": "agent"},
    {"id": "{하위ID2}", "level": 2, "default_role": "agent"}
  ],
  "parent_id": "{상위ID}",
  "level": 1
}
```

---

## 🔧 관련 문서

- [API Specification](03_API_SPECIFICATION.md) - 챗봇 CRUD API
- [Architecture](02_ARCHITECTURE.md) - 위임 메커니즘 상세 설명
- [Data Model](04_DATA_MODEL.md) - ChatbotDef 스키마
