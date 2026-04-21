from __future__ import annotations
"""
retrieval/ingestion_client.py - Ingestion 서버 API 클라이언트
새 API 스펙:
{
  "query": "string",
  "index_names": ["string"],
  "top_k": 5,
  "threshold": 0
}
"""
import requests
import urllib3

from backend.config import settings

# 사내망 SSL 경고 억제
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class IngestionClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self._base_url = (base_url or settings.INGESTION_BASE_URL).rstrip("/")
        self._api_key = api_key or settings.INGESTION_API_KEY
        self._session = requests.Session()
        self._session.verify = settings.SSL_VERIFY
        
        # API 키가 있으면 헤더에 추가 (x-api-key 형식)
        if self._api_key:
            self._session.headers.update({"x-api-key": self._api_key})

    def search(
        self,
        db_ids: list[str],
        query: str,
        k: int = 5,
        filter_metadata: dict | None = None,
        threshold: float = 0.0,
    ) -> list[dict]:
        """
        POST /search
        통합 검색 API
        
        Args:
            db_ids: 검색할 인덱스 이름 목록 (구: db_ids)
            query: 검색 쿼리
            k: 반환할 결과 수 (구: k → top_k)
            filter_metadata: 필터 메타데이터 (선택)
            threshold: 유사도 임계값 (선택, 기본 0)
        """
        if not db_ids:
            return []

        payload: dict = {
            "query": query,
            "index_names": db_ids,  # 변경: db_ids → index_names
            "top_k": k,  # 변경: k → top_k
            "threshold": threshold,  # 추가
        }
        
        if filter_metadata:
            payload["filter_metadata"] = filter_metadata

        try:
            print(f"[DEBUG IngestionClient] POST {self._base_url}/search")
            print(f"[DEBUG IngestionClient] payload: {payload}")
            resp = self._session.post(
                f"{self._base_url}/search",
                json=payload,
                timeout=30,
            )
            print(f"[DEBUG IngestionClient] response status: {resp.status_code}")
            data = resp.json()
            print(f"[DEBUG IngestionClient] response data keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
            results = data.get("results", data if isinstance(data, list) else [])
            print(f"[DEBUG IngestionClient] results count: {len(results)}")
            return results
        except requests.exceptions.HTTPError as e:
            # HTTP 에러 (403 Forbidden 등)
            status = e.response.status_code if e.response else "unknown"
            text = e.response.text[:200] if e.response and e.response.text else ""
            print(f"[IngestionClient] search HTTP {status} 에러 (index_names={db_ids}): {text}")
            return []
        except Exception as e:
            print(f"[IngestionClient] search 오류 (index_names={db_ids}): {type(e).__name__}: {e}")
            return []

    def search_single(
        self,
        db_id: str,
        query: str,
        k: int = 5,
        filter_metadata: dict | None = None,
        threshold: float = 0.0,
    ) -> list[dict]:
        """
        단일 인덱스 검색 (backward compatibility)
        """
        return self.search(
            db_ids=[db_id],
            query=query,
            k=k,
            filter_metadata=filter_metadata,
            threshold=threshold,
        )

    def search_multi(
        self,
        db_ids: list[str],
        query: str,
        k: int = 5,
        filter_metadata: dict | None = None,
        threshold: float = 0.0,
    ) -> list[dict]:
        """
        다중 인덱스 검색 (backward compatibility)
        """
        return self.search(
            db_ids=db_ids,
            query=query,
            k=k,
            filter_metadata=filter_metadata,
            threshold=threshold,
        )


def format_context(results: list[dict]) -> str:
    """검색 결과를 LLM 프롬프트에 삽입할 컨텍스트 문자열로 변환한다."""
    if not results:
        return "관련 문서를 찾지 못했습니다."
    lines = []
    for i, r in enumerate(results, 1):
        content = r.get("content", r.get("text", str(r)))
        source = r.get("source", r.get("doc_id", r.get("index_name", "")))
        score = r.get("score", r.get("similarity", None))
        line = f"[{i}] {content}"
        if source:
            line += f" (출처: {source})"
        if score is not None:
            line += f" [score: {score:.3f}]"
        lines.append(line)
    return "\n\n".join(lines)
