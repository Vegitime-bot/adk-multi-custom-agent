# 2026-04-08 계층 위임 정책 JSON 샘플

parent/child 계층에서 위임 성능과 정확도를 튜닝하기 위한 샘플 설정.

---

## 1) Parent: 하위 챗봇 전체 종합 모드

```json
{
  "id": "chatbot-parent",
  "name": "Parent Bot",
  "policy": {
    "delegation_threshold": 70,
    "multi_sub_execution": true,
    "max_parallel_subs": 4,
    "synthesis_mode": "parallel"
  },
  "sub_chatbots": [
    {"id": "chatbot-a", "level": 1, "default_role": "agent"},
    {"id": "chatbot-b", "level": 1, "default_role": "agent"},
    {"id": "chatbot-c", "level": 1, "default_role": "agent"},
    {"id": "chatbot-d", "level": 1, "default_role": "agent"}
  ]
}
```

- `multi_sub_execution=true`: 하위 다중 실행
- `max_parallel_subs=4`: child 4개 병렬 실행

---

## 2) Child: child→child 깊이 확장 시 지연 제어

```json
{
  "id": "chatbot-a",
  "name": "Child A",
  "policy": {
    "delegation_threshold": 70,
    "multi_sub_execution": true,
    "max_parallel_subs": 2,
    "synthesis_mode": "parallel",
    "enable_parent_delegation": true
  },
  "sub_chatbots": [
    {"id": "chatbot-a1", "level": 2, "default_role": "agent"},
    {"id": "chatbot-a2", "level": 2, "default_role": "agent"},
    {"id": "chatbot-a3", "level": 2, "default_role": "agent"}
  ]
}
```

- child 레벨에서는 `max_parallel_subs`를 2로 줄여 응답 지연을 완화

---

## 3) 커스텀 child 라우팅 정확도 향상 (선택)

```json
{
  "id": "chatbot-bn",
  "policy": {
    "keywords": ["bn", "bn팀", "bn 모듈", "bn 이슈", "bn 프로젝트"]
  }
}
```

- `policy.keywords`는 하위 선택 점수 계산 시 우선 적용됨
- system_prompt 약어와 함께 사용하면 오선택 감소에 도움

---

## 운영 팁

1. parent는 넓게(4개), child는 좁게(2개)
2. child가 많아질수록 `max_parallel_subs`를 단계별로 줄이기
3. 응답이 느리면 우선 `max_parallel_subs`부터 낮추기
4. 오선택이 반복되면 `policy.keywords`를 팀별로 최소 5~10개 추가
