"""
tests/test_response_synthesizer.py - ResponseSynthesizer 단위 테스트

pytest 실행:
    pytest backend/executors/strategies/tests/test_response_synthesizer.py -v
"""
import pytest
from unittest.mock import MagicMock, Mock

from backend.executors.strategies.response_synthesizer import (
    ParallelSynthesizer,
    SequentialSynthesizer,
    WeightedSynthesizer,
    ChainOfThoughtSynthesizer,
    SynthesisContext,
    create_response_synthesizer,
)


class TestSynthesisContext:
    """SynthesisContext 단위 테스트"""

    def test_default_values(self):
        """기본값 테스트"""
        context = SynthesisContext()
        assert context.parent_context == ""
        assert context.user_message == ""
        assert context.system_prompt == ""

    def test_custom_values(self):
        """사용자 정의 값 테스트"""
        context = SynthesisContext(
            parent_context="상위 컨텍스트",
            user_message="사용자 질문",
            system_prompt="시스템 프롬프트"
        )
        assert context.parent_context == "상위 컨텍스트"
        assert context.user_message == "사용자 질문"
        assert context.system_prompt == "시스템 프롬프트"


class TestSequentialSynthesizer:
    """SequentialSynthesizer 단위 테스트"""

    def test_init_default_separator(self):
        """기본 구분자"""
        synthesizer = SequentialSynthesizer()
        assert synthesizer.separator == "\n\n---\n\n"

    def test_init_custom_separator(self):
        """사용자 정의 구분자"""
        synthesizer = SequentialSynthesizer(separator="\n---\n")
        assert synthesizer.separator == "\n---\n"

    def test_synthesize_empty_responses(self):
        """빈 응답 목록"""
        synthesizer = SequentialSynthesizer()
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[]
        )
        assert result == "❌ 하위 Agent로부터 응답을 받지 못했습니다."

    def test_synthesize_single_response(self):
        """단일 응답"""
        synthesizer = SequentialSynthesizer()
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[("id1", "Agent1", "Response 1")]
        )
        assert "**[Agent1]**" in result
        assert "Response 1" in result

    def test_synthesize_multiple_responses(self):
        """다중 응답"""
        synthesizer = SequentialSynthesizer(separator="\n---\n")
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[
                ("id1", "Agent1", "Response 1"),
                ("id2", "Agent2", "Response 2"),
            ]
        )
        assert "**[1] Agent1**" in result
        assert "**[2] Agent2**" in result
        assert "Response 1" in result
        assert "Response 2" in result
        assert "\n---\n" in result


class TestParallelSynthesizer:
    """ParallelSynthesizer 단위 테스트"""

    def test_init_default_values(self):
        """기본값 초기화"""
        synthesizer = ParallelSynthesizer()
        assert synthesizer.temperature == 0.3
        assert synthesizer.max_tokens == 2048
        assert synthesizer.model == "gpt-4o-mini"

    def test_init_custom_values(self):
        """사용자 정의 값 초기화"""
        synthesizer = ParallelSynthesizer(
            model="gpt-4o",
            temperature=0.5,
            max_tokens=1024
        )
        assert synthesizer.model == "gpt-4o"
        assert synthesizer.temperature == 0.5
        assert synthesizer.max_tokens == 1024

    def test_synthesize_empty_responses(self):
        """빈 응답 목록"""
        synthesizer = SequentialSynthesizer()  # LLM 없이 테스트
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[]
        )
        assert result == "❌ 하위 Agent로부터 응답을 받지 못했습니다."

    def test_synthesize_single_response(self):
        """단일 응답은 직접 반환"""
        synthesizer = SequentialSynthesizer()
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[("id1", "Agent1", "Response 1")]
        )
        assert "**[Agent1]**" in result

    def test_build_synthesis_prompt(self):
        """종합 프롬프트 구성"""
        mock_client = MagicMock()
        synthesizer = ParallelSynthesizer(llm_client=mock_client)
        
        prompt = synthesizer._build_synthesis_prompt(
            parent_context="상위 컨텍스트",
            user_message="사용자 질문",
            sub_responses=[("id1", "Agent1", "Response 1")]
        )
        
        assert "사용자 질문" in prompt['user']
        assert "상위 컨텍스트" in prompt['user']
        assert "Agent1" in prompt['user']
        assert "Response 1" in prompt['user']
        assert "통합 어시스턴트" in prompt['system']


class TestWeightedSynthesizer:
    """WeightedSynthesizer 단위 테스트"""

    def test_init_default_weight_calculator(self):
        """기본 가중치 계산기"""
        synthesizer = WeightedSynthesizer()
        weight = synthesizer.weight_calculator("id", "name", "response")
        assert weight == 1.0

    def test_init_custom_weight_calculator(self):
        """사용자 정의 가중치 계산기"""
        custom_calc = lambda sid, name, resp: len(resp) / 100.0
        synthesizer = WeightedSynthesizer(weight_calculator=custom_calc)
        
        weight = synthesizer.weight_calculator("id", "name", "short")
        assert weight == 0.05

    def test_synthesize_single_response(self):
        """단일 응답"""
        synthesizer = SequentialSynthesizer()  # 폴백 테스트
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[("id1", "Agent1", "Response 1")]
        )
        assert "**[Agent1]**" in result


class TestChainOfThoughtSynthesizer:
    """ChainOfThoughtSynthesizer 단위 테스트"""

    def test_init_default_model(self):
        """기본 모델"""
        synthesizer = ChainOfThoughtSynthesizer()
        assert synthesizer.model == "gpt-4o"

    def test_init_custom_model(self):
        """사용자 정의 모델"""
        synthesizer = ChainOfThoughtSynthesizer(model="gpt-4o-mini")
        assert synthesizer.model == "gpt-4o-mini"

    def test_synthesize_empty_responses(self):
        """빈 응답 목록"""
        synthesizer = SequentialSynthesizer()  # 폴백
        result = synthesizer.synthesize(
            parent_context="",
            user_message="test",
            sub_responses=[]
        )
        assert result == "❌ 하위 Agent로부터 응답을 받지 못했습니다."


class TestFactoryFunction:
    """팩토리 함수 테스트"""

    def test_create_parallel_synthesizer(self):
        """parallel 종합기 생성"""
        synthesizer = create_response_synthesizer('parallel', model="gpt-4o-mini")
        assert isinstance(synthesizer, ParallelSynthesizer)
        assert synthesizer.model == "gpt-4o-mini"

    def test_create_sequential_synthesizer(self):
        """sequential 종합기 생성"""
        synthesizer = create_response_synthesizer('sequential')
        assert isinstance(synthesizer, SequentialSynthesizer)

    def test_create_weighted_synthesizer(self):
        """weighted 종합기 생성"""
        synthesizer = create_response_synthesizer('weighted')
        assert isinstance(synthesizer, WeightedSynthesizer)

    def test_create_chain_of_thought_synthesizer(self):
        """chain_of_thought 종합기 생성"""
        synthesizer = create_response_synthesizer('chain_of_thought')
        assert isinstance(synthesizer, ChainOfThoughtSynthesizer)

    def test_create_unknown_synthesizer(self):
        """알 수 없는 종합기 타입 → ValueError"""
        with pytest.raises(ValueError) as exc_info:
            create_response_synthesizer('unknown')

        assert "Unknown synthesizer_type" in str(exc_info.value)
