# TESTING.md - Multi Custom Agent Service 테스트 전략

## 스택
- Language: Python
- Web Framework: FastAPI
- HTTP Client: requests
- Test Framework: pytest (추가 예정)

---

## 전략: 단위 + 통합 병행

| 레벨 | 방식 | 목적 |
|------|------|------|
| 단위 테스트 | Mock/Stub (unittest.mock) | 권한 로직(scope 교집합, db_ids 생성) 빠르게 검증 |
| 통합 테스트 | Mock Ingestion Server (FastAPI) | 실제 요청 흐름 end-to-end 검증 |

---

## 옵션 A — Mock Ingestion Server

파일: `mock_ingestion_server.py`

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

# 목업 데이터: db_id → 검색 결과
MOCK_DATA = {
    "db_001": [{"doc_id": "a1", "content": "문서 A"}],
    "db_002": [{"doc_id": "b1", "content": "문서 B"}],
    "db_003": [{"doc_id": "c1", "content": "문서 C"}],
}

class SearchRequest(BaseModel):
    query: str
    db_ids: List[str]

@app.post("/search")
async def search(req: SearchRequest):
    results = []
    for db_id in req.db_ids:
        results.extend(MOCK_DATA.get(db_id, []))

    return {
        "query": req.query,
        "db_ids_received": req.db_ids,  # 권한 검사 결과가 올바르게 왔는지 확인용
        "results": results
    }
```

실행:
```bash
uvicorn mock_ingestion_server:app --port 8001
```

---

## 옵션 B — 단위 테스트 (Stub)

### ingestion 클라이언트 추상화

파일: `ingestion_client.py`

```python
import requests

def search(query: str, db_ids: list, base_url: str) -> dict:
    resp = requests.post(f"{base_url}/search", json={
        "query": query,
        "db_ids": db_ids
    })
    return resp.json()
```

### 테스트 케이스

파일: `test_auth_scope.py`

```python
from unittest.mock import patch

def test_final_scope_is_intersection():
    chatbot_scope = {"db_001", "db_002"}
    user_scope = {"db_002", "db_003"}
    final_scope = chatbot_scope & user_scope  # 교집합

    assert final_scope == {"db_002"}

def test_search_uses_authorized_db_ids_only():
    with patch("ingestion_client.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"results": []}

        from ingestion_client import search
        search(query="test", db_ids=["db_002"], base_url="http://mock")

        called_db_ids = mock_post.call_args[1]["json"]["db_ids"]
        assert "db_001" not in called_db_ids  # 권한 없는 DB는 절대 안 들어가야 함
```

---

## 핵심 검증 포인트

1. `final_scope = chatbot_scope ∩ user_scope` 교집합 계산이 올바른지
2. ingestion 서버로 전달되는 `db_ids`가 권한 검사를 통과한 것만 포함되는지
3. 권한 없는 `db_id`는 절대 요청에 포함되지 않는지
4. explicit deny가 allow보다 우선하는지

---

## requirements.txt 추가 항목
```
fastapi
uvicorn
pytest
```

---

_마지막 업데이트: 2026-03-26_
