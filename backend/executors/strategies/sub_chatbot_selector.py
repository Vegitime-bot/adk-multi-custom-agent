"""
executors/strategies/sub_chatbot_selector.py - 하위 챗봇 선택 전략 (Strategy Pattern)

하위 챗봇 선택을 위한 Strategy 패턴 구현:
- SubChatbotSelector: 하위 챗봇 선택 기본 인터페이스
- HybridSelector: 키워드 + 임베딩 하이브리드 선택
- KeywordOnlySelector: 키워드 기반 선택
- EmbeddingOnlySelector: 임베딩 기반 선택

사용 예시:
    selector = HybridSelector(
        keyword_weight=0.4,
        embedding_weight=0.6,
        threshold=0.15,
    )
    candidates = selector.select(message, sub_chatbots, chatbot_manager, embedding_service)
    # [(ChatbotDef, selection_info, scores), ...]
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any, Callable
import logging
import re

from backend.core.models import ChatbotDef

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class SelectionScore:
    """선택 점수"""
    keyword: float = 0.0
    embedding: float = 0.0
    hybrid: float = 0.0


class SubChatbotSelector(ABC):
    """
    하위 챗봇 선택 Strategy 인터페이스

    메시지에 가장 적합한 하위 챗봇을 선택하는 전략을 정의합니다.
    런타임에 다른 Selector로 교체 가능합니다.
    """

    @abstractmethod
    def select(
        self,
        message: str,
        sub_chatbot_refs: List[Any],
        chatbot_manager: Any,
        embedding_service: Any = None,
        max_results: int = 1,
    ) -> List[Tuple[ChatbotDef, str, Dict[str, float]]]:
        """
        하위 챗봇 선택

        Args:
            message: 사용자 메시지
            sub_chatbot_refs: 하위 챗봇 참조 리스트 (SubChatbotRef)
            chatbot_manager: 챗봇 매니저 인스턴스
            embedding_service: 임베딩 서비스 인스턴스
            max_results: 최대 결과 수

        Returns:
            선택된 챗봇 리스트 [(ChatbotDef, selection_info, scores), ...]
        """
        pass

    def get_name(self) -> str:
        """Selector 이름 반환 (로깅/디버깅용)"""
        return self.__class__.__name__


class HybridSelector(SubChatbotSelector):
    """
    하이브리드 하위 챗봇 선택 Strategy

    키워드 매칭과 임베딩 유사도를 결합하여 하위 챗봇을 선택합니다.
    
    Attributes:
        keyword_weight: 키워드 점수 가중치 (0-1)
        embedding_weight: 임베딩 점수 가중치 (0-1)
        threshold: 선택 임계값 (하이브리드 점수 기준)
        keyword_threshold: 키워드 점수 최소값 (Fail-safe용)
    """

    DEFAULT_KEYWORD_WEIGHT = None  # config에서 동적 로드
    DEFAULT_EMBEDDING_WEIGHT = None  # config에서 동적 로드
    DEFAULT_THRESHOLD = 0.15
    DEFAULT_KEYWORD_THRESHOLD = 0.3

    # 레거시 키워드 매핑 (하위 호환)
    KEYWORDS_MAP = {
        'chatbot-hr-policy': ['정책', '규정', '채용', '평가', '승진', '인사제도', '징계', '인사', '제도'],
        'chatbot-hr': ['인사', 'hr', '복리후생', '인사팀', '인사관리', '사내', '회사'],
        'chatbot-hr-benefit': ['급여', '연차', '휴가', '복지', '보험', '경조사', '교육지원', '수당', '상여', '복리후생', '의료비', '대출', '자금'],
        'chatbot-tech-backend': ['backend', '백엔드', 'python', 'fastapi', 'django', 'db', 'sql', 'api', '서버'],
        'chatbot-tech-frontend': ['frontend', '프론트엔드', 'react', 'vue', 'javascript', 'css', 'html', 'ui', '화면'],
        'chatbot-tech-devops': ['devops', 'docker', 'kubernetes', 'k8s', 'ci/cd', 'infra', '배포', '모니터링', '인프라'],
        'chatbot-rtl-verilog': ['rtl', 'verilog', 'fpga', '반도체', '디지털 회로', 'hdl', '합성'],
        'chatbot-rtl-synthesis': ['synthesis', '합성', '타이밍', '최적화', '면적', '전력'],
    }

    def _get_default_keyword_weight(self) -> float:
        """설정에서 기본 키워드 가중치 로드"""
        try:
            from config import settings
            return settings.HYBRID_KEYWORD_WEIGHT
        except (ImportError, AttributeError):
            return 0.4  # 폴백 기본값

    def __init__(
        self,
        keyword_weight: Optional[float] = None,
        embedding_weight: Optional[float] = None,
        threshold: Optional[float] = None,
        keyword_threshold: Optional[float] = None,
    ):
        """
        Args:
            keyword_weight: 키워드 점수 가중치 (None이면 설정에서 로드)
            embedding_weight: 임베딩 점수 가중치 (None이면 자동 계산)
            threshold: 선택 임계값 (None이면 DEFAULT_THRESHOLD)
            keyword_threshold: 키워드 점수 최소값 (Fail-safe용)
        """
        self.keyword_weight = keyword_weight or self._get_default_keyword_weight()
        # embedding_weight가 None이면 (1 - keyword_weight)로 자동 계산
        if embedding_weight is None:
            self.embedding_weight = 1.0 - self.keyword_weight
        else:
            self.embedding_weight = embedding_weight
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.keyword_threshold = keyword_threshold or self.DEFAULT_KEYWORD_THRESHOLD
        
        # 가중치 정규화
        total = self.keyword_weight + self.embedding_weight
        if total != 1.0:
            self.keyword_weight /= total
            self.embedding_weight /= total
        
        logger.info(
            f"[SubChatbotSelector] Initialized: {self.get_name()} "
            f"(kw={self.keyword_weight:.2f}, emb={self.embedding_weight:.2f}, "
            f"threshold={self.threshold})"
        )

    def select(
        self,
        message: str,
        sub_chatbot_refs: List[Any],
        chatbot_manager: Any,
        embedding_service: Any = None,
        max_results: int = 3,
    ) -> List[Tuple[ChatbotDef, str, Dict[str, float]]]:
        """
        하이브리드 하위 챗봇 선택

        Args:
            message: 사용자 메시지
            sub_chatbot_refs: 하위 챗봇 참조 리스트
            chatbot_manager: 챗봇 매니저 인스턴스
            embedding_service: 임베딩 서비스 인스턴스
            max_results: 최대 결과 수

        Returns:
            선택된 챗봇 리스트 [(ChatbotDef, selection_info, scores), ...]
        """
        if not chatbot_manager or not sub_chatbot_refs:
            return []

        # 챗봇 정의 로드
        candidates = []
        for sub_ref in sub_chatbot_refs:
            sub_def = chatbot_manager.get_active(sub_ref.id)
            if sub_def:
                candidates.append(sub_def)

        if not candidates:
            return []

        # 점수 계산
        message_lower = message.lower()
        scores = []

        for sub_def in candidates:
            try:
                kw_score = self._keyword_score(sub_def, message_lower)
                emb_score = self._embedding_score(message, sub_def, embedding_service)
                hybrid = self.keyword_weight * kw_score + self.embedding_weight * emb_score

                scores.append({
                    'chatbot': sub_def,
                    'keyword': round(kw_score, 3),
                    'embedding': round(emb_score, 3),
                    'hybrid': round(hybrid, 3),
                })
            except Exception as e:
                logger.warning(f"[Selector] Error evaluating {sub_def.id}: {e}")
                continue

        # 정렬
        scores.sort(key=lambda x: x['hybrid'], reverse=True)

        # 임계값 필터링
        filtered = [s for s in scores if s['hybrid'] >= self.threshold]

        # Fail-safe: 임계값 통과 없으면 키워드 점수 기준으로 최소 1개 선택
        if not filtered:
            keyword_matches = [s for s in scores if s['keyword'] >= self.keyword_threshold]
            if keyword_matches:
                keyword_matches.sort(key=lambda x: (x['keyword'], x['hybrid']), reverse=True)
                filtered = keyword_matches[:1]
            elif scores:
                filtered = scores[:1]

        # 결과 구성
        return [
            (
                s['chatbot'],
                f"(kw:{s['keyword']}, emb:{s['embedding']}, hybrid:{s['hybrid']})",
                {'keyword': s['keyword'], 'embedding': s['embedding'], 'hybrid': s['hybrid']},
            )
            for s in filtered[:max_results]
        ]

    def _keyword_score(self, sub_def: ChatbotDef, message_lower: str) -> float:
        """키워드 매칭 점수 (0-1 정규화)"""
        keywords = []

        # 1) policy.keywords 확인
        if getattr(sub_def, 'policy', None):
            keywords = sub_def.policy.get('keywords', []) or []

        # 2) policy에 없으면 chatbot.keywords 속성 확인
        if not keywords and getattr(sub_def, 'keywords', None):
            keywords = sub_def.keywords

        # 3) 둘 다 없으면 KEYWORDS_MAP 확인 (레거시)
        if not keywords:
            keywords = self.KEYWORDS_MAP.get(sub_def.id, [])

        if not keywords:
            return 0.0

        matched = sum(1 for kw in keywords if kw.lower() in message_lower)
        score = min(matched / max(len(keywords) * 0.3, 1), 1.0)

        return score

    def _embedding_score(
        self,
        message: str,
        sub_def: ChatbotDef,
        embedding_service: Any,
    ) -> float:
        """임베딩 코사인 유사도 점수 (0-1)"""
        if not embedding_service:
            return 0.0

        profile_parts = [sub_def.name, sub_def.description]

        policy_keywords = []
        if getattr(sub_def, 'policy', None):
            policy_keywords = sub_def.policy.get('keywords', []) or []
        keywords = policy_keywords if policy_keywords else self.KEYWORDS_MAP.get(sub_def.id, [])
        if keywords:
            profile_parts.append(' '.join(keywords))

        if sub_def.system_prompt:
            profile_parts.append(sub_def.system_prompt[:200])

        profile_text = ' '.join(profile_parts)
        score = embedding_service.cosine_similarity(message, profile_text)
        return round(score, 2)


class KeywordOnlySelector(SubChatbotSelector):
    """
    키워드 기반 하위 챗봇 선택 Strategy

    순수 키워드 매칭만 사용하여 하위 챗봇을 선택합니다.
    임베딩 서비스가 필요 없어 가볍고 빠릅니다.

    Attributes:
        threshold: 키워드 매칭 최소 비율 (0-1)
    """

    DEFAULT_THRESHOLD = 0.3
    KEYWORDS_MAP = HybridSelector.KEYWORDS_MAP

    def __init__(self, threshold: Optional[float] = None):
        """
        Args:
            threshold: 키워드 매칭 최소 비율 (None이면 DEFAULT_THRESHOLD)
        """
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        logger.info(f"[SubChatbotSelector] Initialized: {self.get_name()} (threshold={self.threshold})")

    def select(
        self,
        message: str,
        sub_chatbot_refs: List[Any],
        chatbot_manager: Any,
        embedding_service: Any = None,
        max_results: int = 3,
    ) -> List[Tuple[ChatbotDef, str, Dict[str, float]]]:
        """
        키워드 기반 하위 챗봇 선택

        Args:
            message: 사용자 메시지
            sub_chatbot_refs: 하위 챗봇 참조 리스트
            chatbot_manager: 챗봇 매니저 인스턴스
            embedding_service: 사용되지 않음
            max_results: 최대 결과 수

        Returns:
            선택된 챗봇 리스트
        """
        if not chatbot_manager or not sub_chatbot_refs:
            return []

        # 챗봇 로드
        candidates = []
        for sub_ref in sub_chatbot_refs:
            sub_def = chatbot_manager.get_active(sub_ref.id)
            if sub_def:
                candidates.append(sub_def)

        if not candidates:
            return []

        # 점수 계산
        message_lower = message.lower()
        scores = []

        for sub_def in candidates:
            kw_score = self._keyword_score(sub_def, message_lower)
            if kw_score >= self.threshold:
                scores.append({
                    'chatbot': sub_def,
                    'keyword': round(kw_score, 3),
                    'embedding': 0.0,
                    'hybrid': round(kw_score, 3),
                })

        # 정렬
        scores.sort(key=lambda x: x['keyword'], reverse=True)

        # 결과 구성
        return [
            (
                s['chatbot'],
                f"(keyword:{s['keyword']})",
                {'keyword': s['keyword'], 'embedding': 0.0, 'hybrid': s['hybrid']},
            )
            for s in scores[:max_results]
        ]

    def _keyword_score(self, sub_def: ChatbotDef, message_lower: str) -> float:
        """키워드 매칭 점수"""
        keywords = []

        if getattr(sub_def, 'policy', None):
            keywords = sub_def.policy.get('keywords', []) or []

        if not keywords and getattr(sub_def, 'keywords', None):
            keywords = sub_def.keywords

        if not keywords:
            keywords = self.KEYWORDS_MAP.get(sub_def.id, [])

        if not keywords:
            return 0.0

        matched = sum(1 for kw in keywords if kw.lower() in message_lower)
        score = min(matched / max(len(keywords) * 0.3, 1), 1.0)

        return score


class EmbeddingOnlySelector(SubChatbotSelector):
    """
    임베딩 기반 하위 챗봇 선택 Strategy

    순수 임베딩 유사도만 사용하여 하위 챗봇을 선택합니다.
    키워드 기반보다 의미적 유사성을 잘 포착합니다.

    Attributes:
        threshold: 임베딩 유사도 임계값 (0-1)
    """

    DEFAULT_THRESHOLD = 0.5

    def __init__(self, threshold: Optional[float] = None):
        """
        Args:
            threshold: 임베딩 유사도 임계값 (None이면 DEFAULT_THRESHOLD)
        """
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        logger.info(f"[SubChatbotSelector] Initialized: {self.get_name()} (threshold={self.threshold})")

    def select(
        self,
        message: str,
        sub_chatbot_refs: List[Any],
        chatbot_manager: Any,
        embedding_service: Any = None,
        max_results: int = 3,
    ) -> List[Tuple[ChatbotDef, str, Dict[str, float]]]:
        """
        임베딩 기반 하위 챗봇 선택

        Args:
            message: 사용자 메시지
            sub_chatbot_refs: 하위 챗봇 참조 리스트
            chatbot_manager: 챗봇 매니저 인스턴스
            embedding_service: 임베딩 서비스 인스턴스 (필수)
            max_results: 최대 결과 수

        Returns:
            선택된 챗봇 리스트
        """
        if not chatbot_manager or not sub_chatbot_refs or not embedding_service:
            return []

        # 챗봇 로드
        candidates = []
        for sub_ref in sub_chatbot_refs:
            sub_def = chatbot_manager.get_active(sub_ref.id)
            if sub_def:
                candidates.append(sub_def)

        if not candidates:
            return []

        # 점수 계산
        scores = []

        for sub_def in candidates:
            try:
                emb_score = self._embedding_score(message, sub_def, embedding_service)
                if emb_score >= self.threshold:
                    scores.append({
                        'chatbot': sub_def,
                        'keyword': 0.0,
                        'embedding': round(emb_score, 3),
                        'hybrid': round(emb_score, 3),
                    })
            except Exception as e:
                logger.warning(f"[Selector] Error evaluating {sub_def.id}: {e}")
                continue

        # 정렬
        scores.sort(key=lambda x: x['embedding'], reverse=True)

        # 결과 구성
        return [
            (
                s['chatbot'],
                f"(embedding:{s['embedding']})",
                {'keyword': 0.0, 'embedding': s['embedding'], 'hybrid': s['hybrid']},
            )
            for s in scores[:max_results]
        ]

    def _embedding_score(
        self,
        message: str,
        sub_def: ChatbotDef,
        embedding_service: Any,
    ) -> float:
        """임베딩 코사인 유사도 점수"""
        profile_parts = [sub_def.name, sub_def.description]

        if sub_def.system_prompt:
            profile_parts.append(sub_def.system_prompt[:200])

        profile_text = ' '.join(profile_parts)
        score = embedding_service.cosine_similarity(message, profile_text)
        return round(score, 2)


def create_sub_chatbot_selector(
    selector_type: str,
    threshold: Optional[float] = None,
    keyword_weight: Optional[float] = None,
    embedding_weight: Optional[float] = None,
) -> SubChatbotSelector:
    """
    하위 챗봇 선택기 팩토리 함수

    Args:
        selector_type: 선택기 타입 ('hybrid', 'keyword', 'embedding')
        threshold: 선택 임계값
        keyword_weight: 하이브리드용 키워드 가중치
        embedding_weight: 하이브리드용 임베딩 가중치

    Returns:
        SubChatbotSelector: 생성된 선택기 인스턴스

    Raises:
        ValueError: 지원하지 않는 selector_type
    """
    if selector_type == 'hybrid':
        return HybridSelector(
            threshold=threshold,
            keyword_weight=keyword_weight,
            embedding_weight=embedding_weight,
        )
    elif selector_type == 'keyword':
        return KeywordOnlySelector(threshold=threshold)
    elif selector_type == 'embedding':
        return EmbeddingOnlySelector(threshold=threshold)
    else:
        raise ValueError(f"Unknown selector_type: {selector_type}. Use 'hybrid', 'keyword', or 'embedding'.")
