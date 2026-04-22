"""
executors/strategies/__init__.py - Strategy 패턴 모듈

HierarchicalAgentExecutor의 복잡한 로직을 Strategy 패턴으로 분해:
- DelegationStrategy: 위임 결정 로직
- SubChatbotSelector: 하위 챗봇 선택 로직
- ResponseSynthesizer: 응답 종합 로직
"""
from __future__ import annotations

from .delegation_strategy import (
    DelegationStrategy,
    DelegateResult,
    ConfidenceThresholdStrategy,
    KeywordMatchStrategy,
    CompositeStrategy,
    create_delegation_strategy,
)

from .sub_chatbot_selector import (
    SubChatbotSelector,
    SelectionScore,
    HybridSelector,
    KeywordOnlySelector,
    EmbeddingOnlySelector,
    create_sub_chatbot_selector,
)

from .response_synthesizer import (
    ResponseSynthesizer,
    SynthesisContext,
    ParallelSynthesizer,
    SequentialSynthesizer,
    WeightedSynthesizer,
    ChainOfThoughtSynthesizer,
    create_response_synthesizer,
)

__all__ = [
    # Delegation Strategy
    'DelegationStrategy',
    'DelegateResult',
    'ConfidenceThresholdStrategy',
    'KeywordMatchStrategy',
    'CompositeStrategy',
    'create_delegation_strategy',
    # Sub Chatbot Selector
    'SubChatbotSelector',
    'SelectionScore',
    'HybridSelector',
    'KeywordOnlySelector',
    'EmbeddingOnlySelector',
    'create_sub_chatbot_selector',
    # Response Synthesizer
    'ResponseSynthesizer',
    'SynthesisContext',
    'ParallelSynthesizer',
    'SequentialSynthesizer',
    'WeightedSynthesizer',
    'ChainOfThoughtSynthesizer',
    'create_response_synthesizer',
]
