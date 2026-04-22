"""
tests/test_hierarchical_executor_integration.py - HierarchicalAgentExecutor Strategy 통합 테스트

pytest 실행:
    pytest backend/executors/strategies/tests/test_hierarchical_executor_integration.py -v
"""
import pytest
from unittest.mock import MagicMock, Mock, patch

from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
from backend.executors.strategies import (
    ConfidenceThresholdStrategy,
    HybridSelector,
    ParallelSynthesizer,
    KeywordOnlySelector,
    SequentialSynthesizer,
)


class MockChatbotDef:
    """Mock ChatbotDef"""
    def __init__(
        self,
        id="test-chatbot",
        name="Test Chatbot",
        description="",
        system_prompt="System prompt",
        db_ids=None,
        policy=None,
        sub_chatbots=None,
        level=0,
        retrieval_k=3,
        max_messages=10,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.level = level
        
        # Retrieval config
        self.retrieval = Mock()
        self.retrieval.db_ids = db_ids or []
        self.retrieval.k = retrieval_k
        self.retrieval.filter_metadata = None
        
        # Memory config
        self.memory = Mock()
        self.memory.max_messages = max_messages
        
        # Policy
        self.policy = policy or {}
        
        # Sub chatbots
        self.sub_chatbots = sub_chatbots or []
        
        # LLM config
        self.llm = Mock()
        self.llm.model = "gpt-4o-mini"


class MockSubChatbotRef:
    """Mock SubChatbotRef"""
    def __init__(self, id):
        self.id = id


class TestHierarchicalAgentExecutorStrategyIntegration:
    """HierarchicalAgentExecutor Strategy 통합 테스트"""

    def test_default_strategy_initialization(self):
        """기본 Strategy 초기화 테스트"""
        chatbot = MockChatbotDef()
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # Strategy가 초기화되었는지 확인
        assert executor._delegation_strategy is not None
        assert executor._sub_chatbot_selector is not None
        assert executor._response_synthesizer is not None
        
        # 기본 Strategy 타입 확인
        assert isinstance(executor._delegation_strategy, ConfidenceThresholdStrategy)
        assert isinstance(executor._sub_chatbot_selector, HybridSelector)
        assert isinstance(executor._response_synthesizer, ParallelSynthesizer)

    def test_custom_strategy_initialization(self):
        """사용자 정의 Strategy 초기화 테스트"""
        chatbot = MockChatbotDef(policy={
            'delegation_strategy_type': 'confidence',
            'sub_chatbot_selector_type': 'keyword',
            'synthesis_mode': 'sequential',
            'delegation_threshold': 80,
        })
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # Policy 기반 Strategy 초기화
        assert isinstance(executor._delegation_strategy, ConfidenceThresholdStrategy)
        assert executor._delegation_strategy.threshold == 80
        assert isinstance(executor._sub_chatbot_selector, KeywordOnlySelector)
        assert isinstance(executor._response_synthesizer, SequentialSynthesizer)

    def test_strategy_injection(self):
        """런타임 Strategy 주입 테스트"""
        chatbot = MockChatbotDef()
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # Strategy 교체
        new_delegation = ConfidenceThresholdStrategy(threshold=50)
        new_selector = KeywordOnlySelector(threshold=0.5)
        new_synthesizer = SequentialSynthesizer(separator="\n---\n")
        
        executor.set_delegation_strategy(new_delegation)
        executor.set_sub_chatbot_selector(new_selector)
        executor.set_response_synthesizer(new_synthesizer)
        
        # 교재되었는지 확인
        assert executor._delegation_strategy is new_delegation
        assert executor._sub_chatbot_selector is new_selector
        assert executor._response_synthesizer is new_synthesizer

    def test_delegation_strategy_usage(self):
        """DelegationStrategy 사용 테스트"""
        chatbot = MockChatbotDef(policy={'delegation_threshold': 70})
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # Strategy 결정 테스트
        result = executor._delegation_strategy.decide(
            confidence=80,
            has_sub_chatbots=True,
            message="test"
        )
        
        assert result.target == 'self'
        
        result = executor._delegation_strategy.decide(
            confidence=50,
            has_sub_chatbots=True,
            message="test"
        )
        
        assert result.target == 'sub'

    def test_policy_compatibility(self):
        """기존 정책과의 호환성 테스트"""
        # 기존 정책 설정으로 초기화
        chatbot = MockChatbotDef(policy={
            'delegation_threshold': 60,
            'multi_sub_execution': True,
            'max_parallel_subs': 5,
            'synthesis_mode': 'parallel',
            'hybrid_score_threshold': 0.2,
            'enable_parent_delegation': True,
        })
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # 정책 설정이 Strategy에 반영되었는지 확인
        assert executor.delegation_threshold == 60
        assert executor.multi_sub_execution == True
        assert executor.max_parallel_subs == 5
        assert executor.synthesis_mode == 'parallel'
        assert executor.hybrid_score_threshold == 0.2
        assert executor.enable_parent_delegation == True
        
        # DelegationStrategy에도 반영되었는지 확인
        assert executor._delegation_strategy.threshold == 60

    def test_sub_chatbot_selector_with_policy(self):
        """Policy 기반 SubChatbotSelector 초기화"""
        chatbot = MockChatbotDef(policy={
            'sub_chatbot_selector_type': 'hybrid',
            'hybrid_score_threshold': 0.25,
        })
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        assert isinstance(executor._sub_chatbot_selector, HybridSelector)
        assert executor._sub_chatbot_selector.threshold == 0.25


class TestStrategyFactoryMethods:
    """Strategy 팩토리 메서드 테스트"""

    def test_create_from_policy(self):
        """Policy에서 Strategy 생성"""
        policy = {
            'delegation_strategy_type': 'confidence',
            'sub_chatbot_selector_type': 'keyword',
            'synthesis_mode': 'sequential',
            'delegation_threshold': 65,
            'hybrid_score_threshold': 0.18,
        }
        
        chatbot = MockChatbotDef(policy=policy)
        ingestion = MagicMock()
        memory = MagicMock()
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=ingestion,
            memory_manager=memory,
        )
        
        # Strategy 생성 확인
        assert executor._delegation_strategy.get_name() == "ConfidenceThresholdStrategy"
        assert executor._sub_chatbot_selector.get_name() == "KeywordOnlySelector"
        assert executor._response_synthesizer.get_name() == "SequentialSynthesizer"
