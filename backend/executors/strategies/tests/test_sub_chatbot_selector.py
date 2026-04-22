"""
tests/test_sub_chatbot_selector.py - SubChatbotSelector 단위 테스트

pytest 실행:
    pytest backend/executors/strategies/tests/test_sub_chatbot_selector.py -v
"""
import pytest
from unittest.mock import MagicMock, Mock

from backend.executors.strategies.sub_chatbot_selector import (
    HybridSelector,
    KeywordOnlySelector,
    EmbeddingOnlySelector,
    SelectionScore,
    create_sub_chatbot_selector,
)


class MockChatbotDef:
    """Mock ChatbotDef"""
    def __init__(self, id, name, description="", system_prompt="", policy=None, keywords=None):
        self.id = id
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.policy = policy or {}
        self.keywords = keywords or []


class MockEmbeddingService:
    """Mock EmbeddingService"""
    def cosine_similarity(self, text1, text2):
        # 단순한 유사도 계산 (테스트용)
        return 0.8 if "similar" in text1.lower() or "similar" in text2.lower() else 0.3


class TestSelectionScore:
    """SelectionScore 단위 테스트"""

    def test_default_values(self):
        """기본값 테스트"""
        score = SelectionScore()
        assert score.keyword == 0.0
        assert score.embedding == 0.0
        assert score.hybrid == 0.0

    def test_custom_values(self):
        """사용자 정의 값 테스트"""
        score = SelectionScore(keyword=0.5, embedding=0.7, hybrid=0.6)
        assert score.keyword == 0.5
        assert score.embedding == 0.7
        assert score.hybrid == 0.6


class TestHybridSelector:
    """HybridSelector 단위 테스트"""

    def test_init_default_values(self):
        """기본값 초기화"""
        selector = HybridSelector()
        assert selector.keyword_weight == 0.4
        assert selector.embedding_weight == 0.6
        assert selector.threshold == 0.15

    def test_init_custom_values(self):
        """사용자 정의 값 초기화"""
        selector = HybridSelector(
            keyword_weight=0.5,
            embedding_weight=0.5,
            threshold=0.2
        )
        assert selector.keyword_weight == 0.5
        assert selector.embedding_weight == 0.5
        assert selector.threshold == 0.2

    def test_weight_normalization(self):
        """가중치 정규화"""
        selector = HybridSelector(
            keyword_weight=1.0,
            embedding_weight=1.0
        )
        assert selector.keyword_weight == 0.5
        assert selector.embedding_weight == 0.5

    def test_select_returns_empty_no_chatbot_manager(self):
        """chatbot_manager 없으면 빈 리스트"""
        selector = HybridSelector()
        result = selector.select(
            message="test message",
            sub_chatbot_refs=[],
            chatbot_manager=None
        )
        assert result == []

    def test_select_returns_empty_no_subs(self):
        """sub_chatbot_refs 없으면 빈 리스트"""
        selector = HybridSelector()
        result = selector.select(
            message="test message",
            sub_chatbot_refs=[],
            chatbot_manager=MagicMock()
        )
        assert result == []

    def test_keyword_score_with_policy_keywords(self):
        """policy.keywords 기반 점수 계산"""
        selector = HybridSelector()
        chatbot = MockChatbotDef(
            id="test1",
            name="Test Chatbot",
            policy={'keywords': ['python', 'backend']}
        )
        
        score = selector._keyword_score(chatbot, "python backend development")
        assert score > 0

    def test_keyword_score_no_keywords(self):
        """키워드 없으면 0점"""
        selector = HybridSelector()
        chatbot = MockChatbotDef(id="test1", name="Test", policy={})
        
        score = selector._keyword_score(chatbot, "test message")
        assert score == 0.0


class TestKeywordOnlySelector:
    """KeywordOnlySelector 단위 테스트"""

    def test_init_default_threshold(self):
        """기본 임계값"""
        selector = KeywordOnlySelector()
        assert selector.threshold == 0.3

    def test_init_custom_threshold(self):
        """사용자 정의 임계값"""
        selector = KeywordOnlySelector(threshold=0.5)
        assert selector.threshold == 0.5

    def test_keyword_score_calculation(self):
        """키워드 점수 계산"""
        selector = KeywordOnlySelector()
        chatbot = MockChatbotDef(
            id="test1",
            name="Test",
            policy={'keywords': ['python', 'backend', 'api']}
        )
        
        # 3개 키워드 중 2개 매칭
        score = selector._keyword_score(chatbot, "python api development")
        expected = min(2 / max(3 * 0.3, 1), 1.0)
        assert score == expected


class TestEmbeddingOnlySelector:
    """EmbeddingOnlySelector 단위 테스트"""

    def test_init_default_threshold(self):
        """기본 임계값"""
        selector = EmbeddingOnlySelector()
        assert selector.threshold == 0.5

    def test_init_custom_threshold(self):
        """사용자 정의 임계값"""
        selector = EmbeddingOnlySelector(threshold=0.7)
        assert selector.threshold == 0.7

    def test_select_no_embedding_service(self):
        """embedding_service 없으면 빈 리스트"""
        selector = EmbeddingOnlySelector()
        result = selector.select(
            message="test",
            sub_chatbot_refs=[Mock()],
            chatbot_manager=MagicMock()
        )
        assert result == []


class TestFactoryFunction:
    """팩토리 함수 테스트"""

    def test_create_hybrid_selector(self):
        """hybrid 선택기 생성"""
        selector = create_sub_chatbot_selector('hybrid', threshold=0.2)
        assert isinstance(selector, HybridSelector)
        assert selector.threshold == 0.2

    def test_create_keyword_selector(self):
        """keyword 선택기 생성"""
        selector = create_sub_chatbot_selector('keyword', threshold=0.4)
        assert isinstance(selector, KeywordOnlySelector)
        assert selector.threshold == 0.4

    def test_create_embedding_selector(self):
        """embedding 선택기 생성"""
        selector = create_sub_chatbot_selector('embedding', threshold=0.6)
        assert isinstance(selector, EmbeddingOnlySelector)
        assert selector.threshold == 0.6

    def test_create_unknown_selector(self):
        """알 수 없는 선택기 타입 → ValueError"""
        with pytest.raises(ValueError) as exc_info:
            create_sub_chatbot_selector('unknown')

        assert "Unknown selector_type" in str(exc_info.value)
