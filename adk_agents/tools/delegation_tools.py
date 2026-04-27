"""
Delegation Tools - 신뢰도 계산 및 하위 챗봇 선택 도구
"""
from typing import List, Dict, Any, Optional
import math

def calculate_confidence(rag_results: List[Dict[str, Any]]) -> float:
    """
    RAG 검색 결과 기반 신뢰도 계산
    
    Args:
        rag_results: 검색 결과 리스트 [{"content": str, "score": float, "source": str}, ...]
        
    Returns:
        0~100 사이의 신뢰도 점수
    """
    if not rag_results:
        return 0.0
    
    # 결과 수 기반 점수 (최대 40점)
    expected_count = 5
    count_score = min(len(rag_results) / expected_count, 1.0) * 40
    
    # 평균 유사도 점수 (최대 60점)
    scores = [r.get("score", 0.0) for r in rag_results]
    avg_score = sum(scores) / len(scores) * 60 if scores else 0
    
    confidence = count_score + avg_score
    return round(min(confidence, 100.0), 2)


def select_sub_chatbot(
    query: str,
    sub_chatbots: List[Dict[str, Any]],
    query_keywords: List[str]
) -> Dict[str, Any]:
    """
    하이브리드 스코어링으로 최적 하위 챗봇 선택
    
    Args:
        query: 사용자 질문
        sub_chatbots: 하위 챗봇 정보 [{"id": str, "name": str, "keywords": [...]}, ...]
        query_keywords: 질문에서 추출된 키워드
        
    Returns:
        선택된 하위 챗봇 정보
    """
    if not sub_chatbots:
        return None
    
    scores = []
    for sub in sub_chatbots:
        # 키워드 매칭 점수 (Jaccard 유사도)
        sub_keywords = set(sub.get("keywords", []))
        query_kw_set = set(query_keywords)
        
        if sub_keywords and query_kw_set:
            intersection = len(sub_keywords & query_kw_set)
            union = len(sub_keywords | query_kw_set)
            keyword_score = intersection / union if union > 0 else 0
        else:
            keyword_score = 0
        
        # 레벨 가중치 (L2 챗봇이 더 전문적이므로 약간의 보너스)
        level = sub.get("level", 1)
        level_bonus = 0.05 if level >= 2 else 0
        
        total_score = keyword_score + level_bonus
        scores.append({
            "chatbot": sub,
            "score": total_score,
            "keyword_score": keyword_score
        })
    
    # 최고 점수 챗봇 선택
    scores.sort(key=lambda x: x["score"], reverse=True)
    best_match = scores[0]
    
    # 임계값(0.15) 미만이면 None 반환
    if best_match["score"] < 0.15:
        return None
    
    return best_match["chatbot"]


def extract_keywords(text: str) -> List[str]:
    """
    텍스트에서 키워드 추출 (간단한 버전)
    실제로는 더 정교한 NLP 사용 가능
    """
    # 불용어 제거 및 토큰화
    stopwords = {"은", "는", "이", "가", "을", "를", "의", "에", "에서", "로", "으로", "와", "과", "하고", "입니다", "있습니다", "하시", "해", "주세요"}
    
    # 한글/영문 단어 추출
    import re
    words = re.findall(r'[가-힣]{2,}|[a-zA-Z]{2,}', text.lower())
    
    # 불용어 제거
    keywords = [w for w in words if w not in stopwords]
    
    return keywords[:10]  # 상위 10개


def should_delegate(
    confidence: float,
    threshold: float = 70.0,
    has_sub_chatbots: bool = True
) -> bool:
    """
    위임 여부 결정
    
    Args:
        confidence: 신뢰도 (0-100)
        threshold: 위임 임계값 (기본 70)
        has_sub_chatbots: 하위 챗봇 존재 여부
        
    Returns:
        위임 필요 여부
    """
    if not has_sub_chatbots:
        return False
    return confidence < threshold


class DelegationContext:
    """위임 결정 컨텍스트"""
    def __init__(
        self,
        chatbot_id: str,
        query: str,
        rag_results: List[Dict],
        confidence: float,
        sub_chatbots: List[Dict] = None,
        parent_id: Optional[str] = None
    ):
        self.chatbot_id = chatbot_id
        self.query = query
        self.rag_results = rag_results
        self.confidence = confidence
        self.sub_chatbots = sub_chatbots or []
        self.parent_id = parent_id
        self.should_delegate = should_delegate(confidence, has_sub_chatbots=bool(sub_chatbots))
        self.selected_sub = None
        
        if self.should_delegate:
            query_keywords = extract_keywords(query)
            self.selected_sub = select_sub_chatbot(query, sub_chatbots, query_keywords)
