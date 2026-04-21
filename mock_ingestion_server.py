"""
mock_ingestion_server.py - Mock Ingestion 서버 (포트 8001)
API_KEY 인증 지원

실행:
    uvicorn mock_ingestion_server:app --port 8001
"""
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Mock Ingestion Server", version="2.0.0")

# 허용된 API 키 (실제 환경에서는 DB나 환경변수에서 관리)
VALID_API_KEYS = [
    "ingestion-server-secret-key",  # .env의 기본값
    os.getenv("INGESTION_API_KEY", "ingestion-server-secret-key"),
]


def verify_api_key(api_key: Optional[str]) -> bool:
    """API 키 검증"""
    if not api_key:
        return False
    return api_key in VALID_API_KEYS


# ── 목업 데이터 ────────────────────────────────────────────────────
MOCK_DATA: dict[str, list[dict]] = {
    "db_001": [
        {"doc_id": "a1", "content": "FastAPI는 Python 기반의 고성능 웹 프레임워크입니다.", "source": "tech_doc_001.txt"},
        {"doc_id": "a2", "content": "uvicorn은 ASGI 서버로 FastAPI와 함께 사용됩니다.", "source": "tech_doc_002.txt"},
    ],
    "db_002": [
        {"doc_id": "b1", "content": "SQLAlchemy는 Python ORM 라이브러리입니다.", "source": "dev_guide_001.txt"},
        {"doc_id": "b2", "content": "PostgreSQL은 오픈소스 관계형 데이터베이스입니다.", "source": "dev_guide_002.txt"},
    ],
    "db_003": [
        {"doc_id": "c1", "content": "연차 신청은 사내 포털을 통해 진행합니다.", "source": "hr_policy_001.txt"},
        {"doc_id": "c2", "content": "복리후생 안내: 의료비 지원, 교육비 지원.", "source": "hr_policy_002.txt"},
    ],
    "db_hr_policy": [
        {"doc_id": "hr_p1", "content": "인사평가제도: 연 2회 자기평가-상사평가.", "source": "hr_policy_detail.txt"},
    ],
    "db_hr_benefit": [
        {"doc_id": "hr_b1", "content": "급여체계: 기본급 + 직급수당 + 성과급.", "source": "salary_guide.txt"},
    ],
    "db_hr_overview": [
        {"doc_id": "hr_ov1", "content": "인사팀 주요 업무: 채용, 교육, 평가.", "source": "hr_overview.txt"},
    ],
    "db_backend": [
        {"doc_id": "be_1", "content": "FastAPI ORM: SQLAlchemy와 함께 사용.", "source": "fastapi_db_guide.txt"},
    ],
    "db_frontend": [
        {"doc_id": "fe_1", "content": "React Hooks: useState, useEffect.", "source": "react_hooks.txt"},
    ],
    "db_devops": [
        {"doc_id": "do_1", "content": "Docker 이미지 최적화.", "source": "docker_best_practice.txt"},
    ],
    "db_tech_overview": [
        {"doc_id": "tech_ov1", "content": "기술지원팀: 소프트웨어 개발 지원.", "source": "tech_overview.txt"},
    ],
}


# ── 새 요청 스키마 ────────────────────────────────────────────────
class SearchRequest(BaseModel):
    """통합 검색 요청"""
    query: str
    index_names: list[str]
    top_k: int = 5
    threshold: float = 0.0


# ── 검색 헬퍼 ─────────────────────────────────────────────────────
def _search_index(index_name: str, query: str, top_k: int, threshold: float) -> list[dict]:
    """지정된 인덱스에서 목업 결과를 반환한다."""
    results = MOCK_DATA.get(index_name, [])
    query_lower = query.lower()
    scored = []
    
    for doc in results:
        content_lower = doc["content"].lower()
        if query_lower in content_lower:
            score = 0.8 + 0.2 * (len(query_lower) / len(content_lower))
        else:
            query_words = query_lower.split()
            matches = sum(1 for word in query_words if len(word) > 1 and word in content_lower)
            score = 0.3 * (matches / max(len(query_words), 1))
        
        if score >= threshold:
            scored.append({
                **doc,
                "score": round(score, 3),
                "index_name": index_name,
            })
    
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── 통합 검색 API (신규 스펙) ───────────────────────────────────
@app.post("/search")
async def search(
    req: SearchRequest,
    api_key: Optional[str] = Header(None, alias="x-api-key")
):
    """
    통합 검색 API
    헤더에 API_KEY 필요
    """
    # API 키 검증
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API_KEY")
    
    if not req.index_names:
        return {
            "query": req.query,
            "index_names": [],
            "total_results": 0,
            "results": [],
        }
    
    all_results = []
    for index_name in req.index_names:
        results = _search_index(index_name, req.query, req.top_k, req.threshold)
        all_results.extend(results)
    
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    final_results = all_results[:req.top_k]
    
    return {
        "query": req.query,
        "index_names": req.index_names,
        "total_results": len(final_results),
        "results": final_results,
    }


# ── 헬스체크 (인증 불필요) ─────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "available_indices": list(MOCK_DATA.keys()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_ingestion_server:app", host="0.0.0.0", port=8001, reload=False)
