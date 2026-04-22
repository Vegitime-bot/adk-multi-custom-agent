"""
tests/test_delegation_strategy.py - DelegationStrategy 단위 테스트

pytest 실행:
    pytest backend/executors/strategies/tests/test_delegation_strategy.py -v
"""
import pytest
from backend.executors.strategies.delegation_strategy import (
    DelegateResult,
    ConfidenceThresholdStrategy,
    KeywordMatchStrategy,
    CompositeStrategy,
    create_delegation_strategy,
)


class TestDelegateResult:
    """DelegateResult 단위 테스트"""

    def test_create_result(self):
        """DelegateResult 생성 테스트"""
        result = DelegateResult(target='self', reason='test reason')
        assert result.target == 'self'
        assert result.reason == 'test reason'

    def test_default_reason(self):
        """기본 reason 테스트"""
        result = DelegateResult(target='sub')
        assert result.target == 'sub'
        assert result.reason == ""


class TestConfidenceThresholdStrategy:
    """ConfidenceThresholdStrategy 단위 테스트"""

    def test_high_confidence_self(self):
        """높은 confidence → self 위임"""
        strategy = ConfidenceThresholdStrategy(threshold=70)
        result = strategy.decide(confidence=80, has_sub_chatbots=True)

        assert result.target == 'self'
        assert "confidence 80% >= threshold 70%" in result.reason

    def test_low_confidence_with_sub(self):
        """낮은 confidence + 하위 챗봇 있음 → sub 위임"""
        strategy = ConfidenceThresholdStrategy(threshold=70)
        result = strategy.decide(confidence=50, has_sub_chatbots=True)

        assert result.target == 'sub'
        assert "confidence 50% < threshold 70%" in result.reason
        assert "has sub_chatbots" in result.reason

    def test_low_confidence_no_sub(self):
        """낮은 confidence + 하위 챗봇 없음 → fallback"""
        strategy = ConfidenceThresholdStrategy(threshold=70)
        result = strategy.decide(confidence=50, has_sub_chatbots=False)

        assert result.target == 'fallback'
        assert "no sub_chatbots" in result.reason

    def test_default_threshold(self):
        """기본 임계값(70) 사용"""
        strategy = ConfidenceThresholdStrategy()
        assert strategy.threshold == 70

    def test_custom_threshold(self):
        """사용자 정의 임계값"""
        strategy = ConfidenceThresholdStrategy(threshold=50)
        assert strategy.threshold == 50

        result = strategy.decide(confidence=60, has_sub_chatbots=True)
        assert result.target == 'self'


class TestKeywordMatchStrategy:
    """KeywordMatchStrategy 단위 테스트"""

    def test_keyword_match_sub(self):
        """키워드 매칭 → sub 위임"""
        keyword_map = {'sub': ['전문', '상세'], 'self': ['간단']}
        strategy = KeywordMatchStrategy(threshold=70, keyword_map=keyword_map)
        result = strategy.decide(
            confidence=80,
            has_sub_chatbots=True,
            message='전문가에게 상세한 답변을 해주세요'
        )

        assert result.target == 'sub'
        assert "keyword match" in result.reason

    def test_keyword_match_self(self):
        """self 키워드 매칭 → self 위임"""
        keyword_map = {'sub': ['전문'], 'self': ['간단']}
        strategy = KeywordMatchStrategy(threshold=70, keyword_map=keyword_map)
        result = strategy.decide(
            confidence=50,  # confidence는 낮지만 키워드가 우선
            has_sub_chatbots=True,
            message='간단하게 설명해주세요'
        )

        assert result.target == 'self'
        assert "keyword match" in result.reason

    def test_no_keyword_match(self):
        """키워드 매칭 없음 → confidence 기반"""
        keyword_map = {'sub': ['전문'], 'self': ['간단']}
        strategy = KeywordMatchStrategy(threshold=70, keyword_map=keyword_map)
        result = strategy.decide(
            confidence=80,
            has_sub_chatbots=True,
            message='어떻게 하나요?'  # 매칭되는 키워드 없음
        )

        assert result.target == 'self'
        assert "confidence 80% >= threshold 70%" in result.reason


class TestCompositeStrategy:
    """CompositeStrategy 단위 테스트"""

    def test_composite_strategy(self):
        """복합 Strategy 테스트"""
        keyword_map = {'sub': ['전문'], 'self': ['간단']}
        keyword_strategy = KeywordMatchStrategy(threshold=70, keyword_map=keyword_map)
        confidence_strategy = ConfidenceThresholdStrategy(threshold=70)

        composite = CompositeStrategy([keyword_strategy, confidence_strategy])

        # 키워드 매칭으로 sub 위임
        result = composite.decide(
            confidence=80,
            has_sub_chatbots=True,
            message='전문가에게 문의'
        )

        assert result.target == 'sub'
        assert "KeywordMatchStrategy" in result.reason


class TestFactoryFunction:
    """팩토리 함수 테스트"""

    def test_create_confidence_strategy(self):
        """confidence Strategy 생성"""
        strategy = create_delegation_strategy('confidence', threshold=60)
        assert isinstance(strategy, ConfidenceThresholdStrategy)
        assert strategy.threshold == 60

    def test_create_keyword_strategy(self):
        """keyword Strategy 생성"""
        keyword_map = {'sub': ['전문']}
        strategy = create_delegation_strategy('keyword', threshold=60, keyword_map=keyword_map)
        assert isinstance(strategy, KeywordMatchStrategy)

    def test_create_composite_strategy(self):
        """composite Strategy 생성"""
        keyword_map = {'sub': ['전문']}
        strategy = create_delegation_strategy('composite', threshold=60, keyword_map=keyword_map)
        assert isinstance(strategy, CompositeStrategy)

    def test_create_unknown_strategy(self):
        """알 수 없는 Strategy 타입 → ValueError"""
        with pytest.raises(ValueError) as exc_info:
            create_delegation_strategy('unknown')

        assert "Unknown strategy_type" in str(exc_info.value)
