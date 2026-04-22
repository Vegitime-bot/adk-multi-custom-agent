# 챗봇 JSON 생성 가이드 (하위 위임 최적화)

## 1. 계층 구조 설계

```
Level 0 (Root): 회사 전체 지원 챗봇
  ├── Level 1 (Parent): 인사지원 상위 챗봇
  │     ├── Level 2 (Child): 인사정책 전문 챗봇
  │     └── Level 2 (Child): 복리후생 전문 챗봇
  └── Level 1 (Parent): 기술지원 상위 챗봇
        ├── Level 2 (Child): 백엔드 개발 전문 챗봇
        └── Level 2 (Child): 프론트엔드 개발 전문 챗봇
```

---

## 2. 각 레벨별 작성 가이드

### Level 0 (Root) - 회사 전체 지원 챗봇

#### description
```json
"description": "회사 전체 업무 지원 Root 챗봇. 인사, 기술 등 모든 문의를 처리하고 전문 부서로 연결"
```

#### system_prompt 핵심
- 모든 사내 문의를 받아 처리
- **신뢰도 70% 미만이거나 전문 상담 필요 시 하위 전문가에게 위임**
- 하위 전문가 목록 명시

```json
"system_prompt": "당신은 회사 전체 업무 지원의 Root 어시스턴트입니다.\n모든 사내 문의를 받아 처리하며, 필요시 각 부서 전문가에게 연결합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 특정 부서의 전문 상담이 필요한 경우 하위 전문가에게 위임하세요\n\n하위 전문가 목록:\n- chatbot-hr: 인사지원 상위 챗봇 (인사정책, 복리후생)\n- chatbot-tech: 기술지원 상위 챗봇 (백엔드, 프론트엔드, DevOps)\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
```

#### keywords (핵심)
- 상위 범주 키워드 포함
- 모든 하위 분야를 커버할 수 있는 **대표 키워드**

```json
"keywords": ["회사", "사내", "업무", "지원", "인사", "기술", "개발", "정책", "규정", "문의"]
```

#### policy 설정
```json
"policy": {
  "delegation_threshold": 70,
  "multi_sub_execution": true,
  "max_parallel_subs": 2,
  "synthesis_mode": "parallel",
  "hybrid_score_threshold": 0.15,
  "enable_parent_delegation": true
}
```

---

### Level 1 (Parent) - 상위 챗봇

#### description
```json
"description": "인사 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임"
```

#### system_prompt 핵심
- 해당 분야의 **모든 문의**를 받아 처리
- **신뢰도 70% 미만 또는 세부 규정 필요 시 하위 전문가 호출 제안**
- 하위 전문가 목록과 **역할 분담** 명시

```json
"system_prompt": "당신은 사내 인사지원의 상위 어시스턴트입니다.\n인사 관련 문의를 받아 먼저 답변을 시도합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 세부 규정/정책이 필요한 경우 하위 전문가 호출을 제안하세요\n\n하위 전문가 목록:\n- chatbot-hr-policy: 인사 정책 및 규정 전문가 (평가, 채용, 승진, 징계 등)\n- chatbot-hr-benefit: 복리후생 및 급여 전문가 (급여, 연차, 휴가, 보험 등)\n\n상위 Agent(chatbot-company)로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
```

#### keywords (핵심)
- 해당 분야의 **모든 키워드** 포함
- 하위 전문가들의 키워드도 **포함** (Parent가 먼저 선택되어야 하므로)

```json
"keywords": ["인사", "hr", "인사팀", "사내", "회사", "정책", "규정", "복리후생", "급여", "평가", "채용", "승진", "연차", "휴가"]
```

#### db_ids
- 해당 분야의 **개요/일반** 문서만 포함
- **세부 전문 문서는 하위 챗봇이 가지도록**

```json
"db_ids": ["db_hr_overview"]
```

#### sub_chatbots
```json
"sub_chatbots": [
  {"id": "chatbot-hr-policy", "level": 1, "default_role": "agent"},
  {"id": "chatbot-hr-benefit", "level": 1, "default_role": "agent"}
]
```

---

### Level 2 (Child) - 하위 전문 챗봇

#### description
```json
"description": "인사 규정, 정책, 인사제도에 특화된 하위 전문가"
```

#### system_prompt 핵심
- **특정 전문 분야에 집중**
- **다른 분야 질문 시 명확히 위임하라고 안내**
- 상위 Agent로부터 위임받은 경우 컨텍스트 활용

```json
"system_prompt": "당신은 사내 인사정책 전문 어시스턴트입니다.\n인사 규정, 채용, 평가, 승진, 직무, 인사제도 등에 대해 정확하게 안내해 주세요.\n검색된 인사 정책 문서를 기반으로 답변하세요.\n\n⚠️ 중요: 다음과 같은 경우 반드시 '해당 내용은 제 전문 분야가 아닙니다. 복리후생 전문 챗봘에게 문의해 주세요.'라고 답변하세요:\n1. 검색 결과가 없는 경우\n2. 급여, 연차, 휴가, 복지, 보험 등 복리후생 관련 내용\n3. 확실하지 않은 내용\n\n상위 Agent(chatbot-hr)로부터 위임받은 경우, 축적된 컨텍스트를 참고하여 더 정확한 답변을 제공하세요.\n\n개인 의견은 배제하고 규정 내용만 안내하세요.\n답변은 한국어로 작성하세요."
```

#### keywords (핵심)
- **해당 전문 분야의 세부 키워드**
- 다른 분야와 **명확히 구분**되는 키워드

```json
"keywords": ["정책", "규정", "평가", "채용", "승진", "인사제도", "징계", "인사", "성과", "보상", "승급"]
```

#### db_ids
- **해당 전문 분야의 상세 문서** 포함

```json
"db_ids": ["db_hr_policy", "db_003"]
```

#### sub_chatbots
```json
"sub_chatbots": []
```

---

## 3. Keywords 작성 원칙

| 레벨 | Keywords 특성 | 예시 |
|------|--------------|------|
| Level 0 (Root) | 전사적, 포괄적 | "회사", "사내", "업무", "지원" |
| Level 1 (Parent) | 분야 전체 + 하위 키워드 포함 | "인사", "hr", "급여", "평가", "연차" |
| Level 2 (Child) | 세부 전문 분야 | "정책", "규정", "평가" (정책) / "급여", "연차", "휴가" (복리후생) |

**중요:** 키워드 개수가 너무 많으면 keyword 점수가 낮아짐 → **7~12개** 정도가 적당

---

## 4. Policy 설정 권장값

| 설정 | Root (L0) | Parent (L1) | Child (L2) |
|------|-----------|-------------|------------|
| `delegation_threshold` | 70 | 70 | 70 (또는 없음) |
| `multi_sub_execution` | true | true | false |
| `max_parallel_subs` | 2~3 | 2 | 0 |
| `synthesis_mode` | "parallel" | "parallel" | - |
| `hybrid_score_threshold` | 0.15 | 0.15 | 0.15 |
| `enable_parent_delegation` | true | true | false |

---

## 5. JSON 템플릿

### chatbot-parent.json (Level 1)

```json
{
  "id": "chatbot-{분야}",
  "name": "{분야}지원 상위 챗봇",
  "description": "{분야} 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임",
  "active": true,
  "capabilities": {
    "db_ids": ["db_{분야}_overview"],
    "model": "gpt-4o-mini",
    "system_prompt": "당신은 사내 {분야}지원의 상위 어시스턴트입니다.\n{분야} 관련 문의를 받아 먼저 답변을 시도합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 세부 전문 상담이 필요한 경우 하위 전문가 호출을 제안하세요\n\n하위 전문가 목록:\n- chatbot-{분야}-sub1: {세부분야1} 전문가\n- chatbot-{분야}-sub2: {세부분야2} 전문가\n\n상위 Agent로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
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
    "max_parallel_subs": 2,
    "synthesis_mode": "parallel",
    "hybrid_score_threshold": 0.15,
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5", "키워드6", "키워드7", "키워드8", "키워드9", "키워드10"]
  },
  "sub_chatbots": [
    {"id": "chatbot-{분야}-sub1", "level": 1, "default_role": "agent"},
    {"id": "chatbot-{분야}-sub2", "level": 1, "default_role": "agent"}
  ],
  "parent_id": "chatbot-company",
  "level": 1
}
```

### chatbot-child.json (Level 2)

```json
{
  "id": "chatbot-{분야}-{세부분야}",
  "name": "{세부분야} 전문 챗봇",
  "description": "{세부분야}에 특화된 하위 전문가",
  "active": true,
  "capabilities": {
    "db_ids": ["db_{분야}_{세부분야}"],
    "model": "gpt-4o-mini",
    "system_prompt": "당신은 사내 {세부분야} 전문 어시스턴트입니다.\n{세부분야}에 대해 정확하게 안내해 주세요.\n검색된 문서를 기반으로 답변하세요.\n\n⚠️ 중요: 다음과 같은 경우 반드시 '해당 내용은 제 전문 분야가 아닙니다. {다른전문가}에게 문의해 주세요.'라고 답변하세요:\n1. 검색 결과가 없는 경우\n2. {다른분야} 관련 내용\n3. 확실하지 않은 내용\n\n상위 Agent로부터 위임받은 경우, 축적된 컨텍스트를 참고하여 더 정확한 답변을 제공하세요.\n\n개인 의견은 배제하고 규정 내용만 안내하세요.\n답변은 한국어로 작성하세요."
  },
  "policy": {
    "temperature": 0.2,
    "max_tokens": 1024,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20,
    "delegation_threshold": 70,
    "enable_parent_delegation": false,
    "keywords": ["세부키워드1", "세부키워드2", "세부키워드3", "세부키워드4", "세부키워드5", "세부키워드6", "세부키워드7"]
  },
  "sub_chatbots": [],
  "parent_id": "chatbot-{분야}",
  "level": 2
}
```

---

## 6. 실제 예시 (인사 분야)

### chatbot-hr.json (Level 1)
```json
{
  "id": "chatbot-hr",
  "name": "인사지원 상위 챗봇",
  "description": "인사 관련 모든 문의를 처리하는 상위 챗봇. 세부 사항은 하위 전문가에게 위임",
  "active": true,
  "capabilities": {
    "db_ids": ["db_hr_overview"],
    "model": "gpt-4o-mini",
    "system_prompt": "당신은 사내 인사지원의 상위 어시스턴트입니다.\n인사 관련 문의를 받아 먼저 답변을 시도합니다.\n\n답변 시 다음을 반드시 준수하세요:\n1. 먼저 질문에 대한 초기 답변을 생성하세요\n2. 답변 끝에 'CONFIDENCE: XX' 형식으로 신뢰도를 표시하세요 (0-100)\n3. 신뢰도가 70% 미만이거나, 세부 규정/정책이 필요한 경우 하위 전문가 호출을 제안하세요\n\n하위 전문가 목록:\n- chatbot-hr-policy: 인사 정책 및 규정 전문가 (평가, 채용, 승진, 징계 등)\n- chatbot-hr-benefit: 복리후생 및 급여 전문가 (급여, 연차, 휴가, 보험 등)\n\n상위 Agent(chatbot-company)로부터 위임받은 경우, 축적된 컨텍스트를 활용하여 답변하세요.\n\n모르는 내용은 모른다고 솔직하게 답변하세요.\n답변은 한국어로 작성하세요."
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
    "max_parallel_subs": 2,
    "synthesis_mode": "parallel",
    "hybrid_score_threshold": 0.15,
    "keywords": ["인사", "hr", "인사팀", "사내", "회사", "정책", "규정", "복리후생", "급여", "평가", "채용", "승진", "연차", "휴가"]
  },
  "sub_chatbots": [
    {"id": "chatbot-hr-policy", "level": 1, "default_role": "agent"},
    {"id": "chatbot-hr-benefit", "level": 1, "default_role": "agent"}
  ],
  "parent_id": "chatbot-company",
  "level": 1
}
```

### chatbot-hr-policy.json (Level 2)
```json
{
  "id": "chatbot-hr-policy",
  "name": "인사정책 전문 챗봇",
  "description": "인사 규정, 정책, 인사제도에 특화된 하위 전문가",
  "active": true,
  "capabilities": {
    "db_ids": ["db_hr_policy", "db_003"],
    "model": "gpt-4o-mini",
    "system_prompt": "당신은 사내 인사정책 전문 어시스턴트입니다.\n인사 규정, 채용, 평가, 승진, 직무, 인사제도 등에 대해 정확하게 안내해 주세요.\n검색된 인사 정책 문서를 기반으로 답변하세요.\n\n⚠️ 중요: 다음과 같은 경우 반드시 '해당 내용은 제 전문 분야가 아닙니다. 복리후생 전문 챗봘에게 문의해 주세요.'라고 답변하세요:\n1. 검색 결과가 없는 경우\n2. 급여, 연차, 휴가, 복지, 보험 등 복리후생 관련 내용\n3. 확실하지 않은 내용\n\n상위 Agent(chatbot-hr)로부터 위임받은 경우, 축적된 컨텍스트를 참고하여 더 정확한 답변을 제공하세요.\n\n개인 의견은 배제하고 규정 내용만 안내하세요.\n답변은 한국어로 작성하세요."
  },
  "policy": {
    "temperature": 0.2,
    "max_tokens": 1024,
    "stream": true,
    "supported_modes": ["tool", "agent"],
    "default_mode": "agent",
    "max_messages": 20,
    "delegation_threshold": 70,
    "enable_parent_delegation": false,
    "keywords": ["정책", "규정", "평가", "채용", "승진", "인사제도", "징계", "인사", "성과", "보상", "승급"]
  },
  "sub_chatbots": [],
  "parent_id": "chatbot-hr",
  "level": 2
}
```

---

*작성일: 2026-04-22*
*버전: v1.0*
