"""
executors/strategies/delegation_strategy.py - 위임 결정 전략 (Strategy Pattern)

위임 대상 결정을 위한 Strategy 패턴 구현:
- DelegationStrategy: 위임 결정 기본 인터페이스
- ConfidenceThresholdStrategy: Confidence 기반 위임 결정
- KeywordMatchStrategy: 키워드 매칭 기반 위임 결정

사용 예시:
    strategy = ConfidenceThresholdStrategy(threshold=70)
    result = strategy.decide(confidence=65, has_sub_chatbots=True)
    # DelegateResult(target='sub', reason='confidence 65% < threshold 70%')
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
import logging

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class DelegateResult:
    """위임 결정 결과"""
    target: str  # 'self', 'sub', 'fallback'
    reason: str = ""


class DelegationStrategy(ABC):
    """
    위임 결정 Strategy 인터페이스
    
    위임 대상(self/sub/fallback) 결정을 위한 전략을 정의합니다.
    런타임에 다른 Strategy로 교체 가능합니다.
    """

    @abstractmethod
    def decide(
        self,
        confidence: float,
        has_sub_chatbots: bool,
        message: str = "",
        context: Dict[str, Any] = None,
    ) -> DelegateResult:
        """
        위임 대상 결정

        Args:
            confidence: 현재 Agent의 Confidence (0-100)
            has_sub_chatbots: 하위 챗봇 존재 여부
            message: 사용자 메시지 (optional - 키워드 분석용)
            context: 추가 컨텍스트 (optional)

        Returns:
            DelegateResult: 위임 결정 결과
        """
        pass

    def get_name(self) -> str:
        """Strategy 이름 반환 (로깅/디버깅용)"""
        return self.__class__.__name__


class ConfidenceThresholdStrategy(DelegationStrategy):
    """
    Confidence 임계값 기반 위임 결정 Strategy
    
    설정된 Confidence 임계값(threshold)을 기준으로 위임 여부를 결정합니다.
    - Confidence >= threshold: 자체 답변 ('self')
    - Confidence < threshold + 하위 챗봇 있음: 하위로 위임 ('sub')
    - Confidence < threshold + 하위 챗봇 없음: Fallback ('fallback')
    
    Attributes:
        threshold: Confidence 임계값 (기본값: config에서 로드)
    """

    DEFAULT_THRESHOLD = None  # config에서 동적 로드

    def _get_default_threshold(self) -> float:
        """설정에서 기본 임계값 로드"""
        try:
            from config import settings
            return settings.DEFAULT_DELEGATION_THRESHOLD
        except (ImportError, AttributeError):
            return 70  # 폴백 기본값

    def __init__(self, threshold: Optional[float] = None):
        """
        Args:
            threshold: Confidence 임계값 (None이면 설정에서 로드)
        """
        self.threshold = threshold or self._get_default_threshold()
        logger.info(f"[DelegationStrategy] Initialized: {self.get_name()} with threshold={self.threshold}%")

    def decide(
        self,
        confidence: float,
        has_sub_chatbots: bool,
        message: str = "",
        context: Dict[str, Any] = None,
    ) -> DelegateResult:
        """
        Confidence 기반 위임 결정

        Args:
            confidence: 현재 Agent의 Confidence (0-100)
            has_sub_chatbots: 하위 챗봇 존재 여부
            message: 사용자 메시지 (사용되지 않음)
            context: 추가 컨텍스트 (사용되지 않음)

        Returns:
            DelegateResult: 위임 결정 결과
        """
        if confidence >= self.threshold:
            # Confidence 충분 → 자체 답변
            return DelegateResult(
                target='self',
                reason=f"confidence {confidence}% >= threshold {self.threshold}%",
            )

        # Confidence 부족
        if has_sub_chatbots:
            return DelegateResult(
                target='sub',
                reason=f"confidence {confidence}% < threshold {self.threshold}%, has sub_chatbots",
            )

        # 하위 챗봇 없음 → Fallback
        return DelegateResult(
            target='fallback',
            reason=f"confidence {confidence}% < threshold {self.threshold}%, no sub_chatbots",
        )


class KeywordMatchStrategy(DelegationStrategy):
    """
    키워드 매칭 기반 위임 결정 Strategy
    
    메시지의 키워드 매칭 결과와 Confidence를 함께 고려하여 위임을 결정합니다.
    특정 키워드가 포함되면 해당 Agent가 처리하도록 유도할 수 있습니다.
    
    Attributes:
        threshold: Confidence 임계값
        keyword_map: 키워드 → 타겟 매핑 (ex: {'sub': ['전문', '상세'], 'self': ['간단']})
    """

    def __init__(
        self,
        threshold: Optional[float] = None,
        keyword_map: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Args:
            threshold: Confidence 임계값 (None이면 설정에서 로드)
            keyword_map: 키워드 → 타겟 매핑
                예: {
                    'sub': ['전문', '상세', '깊은', '심화'],
                    'self': ['간단', '요약', '빠른'],
                }
        """
        # ConfidenceThresholdStrategy의 메서드를 사용하여 설정 로드
        self.threshold = threshold or ConfidenceThresholdStrategy._get_default_threshold(None)
        self.keyword_map = keyword_map or {}
        logger.info(f"[DelegationStrategy] Initialized: {self.get_name()} with keywords={len(self.keyword_map)} groups")

    def decide(
        self,
        confidence: float,
        has_sub_chatbots: bool,
        message: str = "",
        context: Dict[str, Any] = None,
    ) -> DelegateResult:
        """
        키워드 + Confidence 기반 위임 결정

        Args:
            confidence: 현재 Agent의 Confidence (0-100)
            has_sub_chatbots: 하위 챗봇 존재 여부
            message: 사용자 메시지 (키워드 분석용)
            context: 추가 컨텍스트

        Returns:
            DelegateResult: 위임 결정 결과
        """
        message_lower = message.lower()

        # 1. 키워드 기반 선결정
        keyword_match = self._check_keywords(message_lower)
        if keyword_match:
            if keyword_match == 'self' or (keyword_match == 'sub' and has_sub_chatbots):
                return DelegateResult(
                    target=keyword_match,
                    reason=f"keyword match: '{keyword_match}' keywords found in message",
                )

        # 2. Confidence 기반 결정 (ConfidenceThresholdStrategy와 동일한 로직)
        if confidence >= self.threshold:
            return DelegateResult(
                target='self',
                reason=f"confidence {confidence}% >= threshold {self.threshold}%",
            )

        if has_sub_chatbots:
            return DelegateResult(
                target='sub',
                reason=f"confidence {confidence}% < threshold {self.threshold}%, has sub_chatbots",
            )

        return DelegateResult(
            target='fallback',
            reason=f"confidence {confidence}% < threshold {self.threshold}%, no sub_chatbots",
        )

    def _check_keywords(self, message_lower: str) -> Optional[str]:
        """
        메시지에서 키워드 매칭 확인

        Args:
            message_lower: 소문자로 변환된 메시지

        Returns:
            매칭된 타겟 ('self', 'sub') 또는 None
        """
        if not self.keyword_map:
            return None

        # 우선순위: sub > self
        for target in ['sub', 'self']:
            keywords = self.keyword_map.get(target, [])
            if any(kw.lower() in message_lower for kw in keywords):
                return target

        return None


class CompositeStrategy(DelegationStrategy):
    """
    복합 위임 결정 Strategy
    
    여러 Strategy를 체인으로 연결하여 순차적으로 평가합니다.
    첫 번째로 매칭되는 Strategy의 결과를 반환합니다.
    
    Attributes:
        strategies: 평가할 Strategy 리스트 (순서대로)
    """

    def __init__(self, strategies: List[DelegationStrategy]):
        """
        Args:
            strategies: 평가할 Strategy 리스트
        """
        self.strategies = strategies
        logger.info(f"[DelegationStrategy] Initialized: {self.get_name()} with {len(strategies)} strategies")

    def decide(
        self,
        confidence: float,
        has_sub_chatbots: bool,
        message: str = "",
        context: Dict[str, Any] = None,
    ) -> DelegateResult:
        """
        복합 위임 결정

        Args:
            confidence: 현재 Agent의 Confidence (0-100)
            has_sub_chatbots: 하위 챗봇 존재 여부
            message: 사용자 메시지
            context: 추가 컨텍스트

        Returns:
            DelegateResult: 위임 결정 결과
        """
        for strategy in self.strategies:
            result = strategy.decide(confidence, has_sub_chatbots, message, context)
            if result.target != 'fallback' or len(self.strategies) == 1:
                result.reason = f"[{strategy.get_name()}] {result.reason}"
                return result

        # 마지막 Strategy의 결과 반환
        return self.strategies[-1].decide(confidence, has_sub_chatbots, message, context)


def create_delegation_strategy(
    strategy_type: str,
    threshold: Optional[float] = None,
    keyword_map: Optional[Dict[str, List[str]]] = None,
) -> DelegationStrategy:
    """
    위임 Strategy 팩토리 함수

    Args:
        strategy_type: Strategy 타입 ('confidence', 'keyword', 'composite')
        threshold: Confidence 임계값
        keyword_map: 키워드 매핑 (keyword 타입일 때만 사용)

    Returns:
        DelegationStrategy: 생성된 Strategy 인스턴스

    Raises:
        ValueError: 지원하지 않는 strategy_type
    """
    if strategy_type == 'confidence':
        return ConfidenceThresholdStrategy(threshold=threshold)
    elif strategy_type == 'keyword':
        return KeywordMatchStrategy(threshold=threshold, keyword_map=keyword_map)
    elif strategy_type == 'composite':
        # 기본 복합: keyword + confidence
        keyword_strategy = KeywordMatchStrategy(threshold=threshold, keyword_map=keyword_map)
        confidence_strategy = ConfidenceThresholdStrategy(threshold=threshold)
        return CompositeStrategy([keyword_strategy, confidence_strategy])
    else:
        raise ValueError(f"Unknown strategy_type: {strategy_type}. Use 'confidence', 'keyword', or 'composite'.")
