"""
backend/services/embedding_service.py - 임베딩 서비스
하위 Agent 선택 및 유사도 계산을 위한 임베딩 서비스
"""
import os
from typing import List, Optional

import numpy as np


class EmbeddingService:
    """
    텍스트 임베딩 서비스
    - 실제 환경: OpenAI, SentenceTransformers 등 사용
    - Mock: 간단한 TF-IDF 기반 벡터화 (데모용)
    """
    
    def __init__(self):
        self._cache = {}  # 텍스트 -> 벡터 캐시
        self._vocab = set()  # 전체 단어 사전
        
    def _tokenize(self, text: str) -> List[str]:
        """간단한 토큰화 (한글/영문 지원)"""
        import re
        # 한글, 영문, 숫자 추출
        tokens = re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())
        return tokens
    
    def _get_vector(self, text: str) -> np.ndarray:
        """텍스트를 벡터로 변환 (Mock 구현)"""
        if text in self._cache:
            return self._cache[text]
        
        tokens = self._tokenize(text)
        
        # 간단한 해싱 기반 벡터 (실제로는 사전학습 모델 사용)
        # 각 토큰을 해시값으로 변환하여 평균
        if not tokens:
            vec = np.zeros(128)
        else:
            hashes = [hash(token) % 10000 for token in tokens]
            # 128차원 벡터 생성
            vec = np.zeros(128)
            for h in hashes:
                vec[h % 128] += 1
            # 정규화
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
        
        self._cache[text] = vec
        return vec
    
    def get_embedding(self, text: str) -> List[float]:
        """텍스트 임베딩 벡터 반환"""
        vec = self._get_vector(text)
        return vec.tolist()
    
    def cosine_similarity(self, text1: str, text2: str) -> float:
        """두 텍스트 간 코사인 유사도 계산"""
        vec1 = self._get_vector(text1)
        vec2 = self._get_vector(text2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def find_most_similar(self, query: str, candidates: List[tuple]) -> Optional[tuple]:
        """
        가장 유사한 후보 찾기
        
        Args:
            query: 검색할 텍스트
            candidates: [(id, text), ...] 형태의 후보 리스트
        
        Returns:
            (id, similarity_score) 또는 None
        """
        if not candidates:
            return None
        
        best_id = None
        best_score = -1
        
        for candidate_id, candidate_text in candidates:
            score = self.cosine_similarity(query, candidate_text)
            if score > best_score:
                best_score = score
                best_id = candidate_id
        
        return (best_id, best_score) if best_id else None


# 싱글톤 인스턴스
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """임베딩 서비스 싱글톤 반환"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def reset_embedding_service():
    """테스트용: 임베딩 서비스 재설정"""
    global _embedding_service
    _embedding_service = None
