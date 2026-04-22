"""
executors/strategies/response_synthesizer.py - 응답 종합 전략 (Strategy Pattern)

다중 하위 Agent 응답을 종합하기 위한 Strategy 패턴 구현:
- ResponseSynthesizer: 응답 종합 기본 인터페이스
- ParallelSynthesizer: 병렬 응답 종합 (LLM 기반)
- SequentialSynthesizer: 순차 응답 종합 (단순 연결)
- WeightedSynthesizer: 가중치 기반 응답 종합

사용 예시:
    synthesizer = ParallelSynthesizer(llm_client=client, model="gpt-4")
    response = synthesizer.synthesize(
        parent_context="상위 컨텍스트",
        user_message="사용자 질문",
        sub_responses=[(id1, name1, resp1), (id2, name2, resp2)],
    )
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from backend.llm.client import get_llm_client

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class SynthesisContext:
    """종합 컨텍스트"""
    parent_context: str = ""
    user_message: str = ""
    system_prompt: str = ""


class ResponseSynthesizer(ABC):
    """
    응답 종합 Strategy 인터페이스

    여러 하위 Agent의 응답을 하나로 종합하는 전략을 정의합니다.
    런타임에 다른 Synthesizer로 교체 가능합니다.
    """

    @abstractmethod
    def synthesize(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """
        응답 종합

        Args:
            parent_context: 상위 Agent의 검색 컨텍스트
            user_message: 사용자 질문
            sub_responses: 하위 Agent 응답 리스트 [(id, name, response), ...]

        Returns:
            str: 종합된 응답
        """
        pass

    def get_name(self) -> str:
        """Synthesizer 이름 반환 (로깅/디버깅용)"""
        return self.__class__.__name__


class ParallelSynthesizer(ResponseSynthesizer):
    """
    병렬 응답 종합 Strategy

    LLM을 사용하여 여러 하위 Agent 응답을 병렬로 분석하고
    하나의 일관된 응답으로 종합합니다.

    Attributes:
        llm_client: LLM 클라이언트 인스턴스
        model: 사용할 LLM 모델명
        temperature: 생성 온도
        max_tokens: 최대 토큰 수
    """

    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_MAX_TOKENS = 2048

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "gpt-4o-mini",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Args:
            llm_client: LLM 클라이언트 (None이면 기본값 사용)
            model: LLM 모델명
            temperature: 생성 온도
            max_tokens: 최대 토큰 수
        """
        self.llm_client = llm_client or get_llm_client()
        self.model = model
        self.temperature = temperature or self.DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        
        logger.info(
            f"[ResponseSynthesizer] Initialized: {self.get_name()} "
            f"(model={self.model}, temp={self.temperature})"
        )

    def synthesize(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """
        LLM 기반 병렬 응답 종합

        Args:
            parent_context: 상위 Agent의 검색 컨텍스트
            user_message: 사용자 질문
            sub_responses: 하위 Agent 응답 리스트 [(id, name, response), ...]

        Returns:
            str: 종합된 응답
        """
        if not sub_responses:
            logger.warning("[Synthesizer] No sub-responses to synthesize")
            return "❌ 하위 Agent로부터 응답을 받지 못했습니다."

        if len(sub_responses) == 1:
            # 단일 응답은 직접 반환
            _, name, response = sub_responses[0]
            logger.info(f"[Synthesizer] Single response from {name}, returning directly")
            return f"**[{name}]**\n\n{response}"

        logger.info(f"[Synthesizer] Synthesizing {len(sub_responses)} responses with LLM")

        # 프롬프트 구성
        synthesis_prompt = self._build_synthesis_prompt(
            parent_context, user_message, sub_responses
        )

        try:
            # LLM 호출
            messages = [
                {"role": "system", "content": synthesis_prompt["system"]},
                {"role": "user", "content": synthesis_prompt["user"]},
            ]
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
            
            synthesized = response.choices[0].message.content or ""
            
            # 참고 전문가 목록 추가
            expert_names = [f"[{name}]" for _, name, _ in sub_responses]
            synthesized += "\n\n---\n**참고 전문가:** " + ", ".join(expert_names)
            
            logger.info(f"[Synthesizer] LLM synthesis completed ({len(synthesized)} chars)")
            return synthesized
            
        except Exception as e:
            logger.error(f"[Synthesizer] LLM synthesis failed: {e}")
            return self._fallback_synthesis(sub_responses)

    def _build_synthesis_prompt(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> Dict[str, str]:
        """응답 종합을 위한 프롬프트 구성"""
        experts_text = "\n\n".join(
            f"### [{sub_name}]\n{response.strip()}"
            for _, sub_name, response in sub_responses
        )

        system_prompt = """당신은 여러 전문가 챗봇의 응답을 종합하는 통합 어시스턴트입니다.

사용자의 질문에 대해 여러 전문가가 각자의 관점에서 답변했습니다.
이를 하나의 일관된 응답으로 정리해주세요.

종합 시 다음 원칙을 따르세요:
1. 중복되는 내용은 한 번만 포함하고, 보강되는 내용은 합쳐주세요
2. 각 전문가의 핵심 포인트를 유지하되, 자연스러운 흐름으로 연결하세요
3. 필요시 [전문가명] 형식으로 출처를 표기하세요
4. 사용자 질문의 모든 측면을 다루었는지 확인하세요
5. 모순되는 정보가 있다면, 더 신뢰할 수 있는 측면을 우선시하되 양쪽 의견을 명시하세요

답변은 한국어로 작성하세요."""

        user_prompt = f"""**사용자 질문:**
{user_message}

**상위 Agent 검색 컨텍스트:**
{parent_context[:500] if parent_context else "(컨텍스트 없음)"}

**전문가별 응답:**
{experts_text}

위 전문가들의 응답을 종합하여 사용자에게 하나의 일관된 답변을 제공해주세요."""

        return {'system': system_prompt, 'user': user_prompt}

    def _fallback_synthesis(
        self,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """LLM 종합 실패 시 수동 종합"""
        parts = ["다음은 관련 전문가들의 답변을 종합한 내용입니다:\n"]
        for _, sub_name, response in sub_responses:
            parts.append(f"\n**[{sub_name}]**\n{response}")
        return "\n".join(parts)


class SequentialSynthesizer(ResponseSynthesizer):
    """
    순차 응답 종합 Strategy

    하위 Agent 응답을 순서대로 연결하여 하나의 응답으로 만듭니다.
    LLM을 사용하지 않아 가볍고 빠릅니다.

    Attributes:
        separator: 응답 구분자
    """

    def __init__(self, separator: str = "\n\n---\n\n"):
        """
        Args:
            separator: 응답 사이 구분자
        """
        self.separator = separator
        logger.info(f"[ResponseSynthesizer] Initialized: {self.get_name()}")

    def synthesize(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """
        순차 응답 종합

        Args:
            parent_context: 상위 Agent의 검색 컨텍스트 (사용되지 않음)
            user_message: 사용자 질문 (사용되지 않음)
            sub_responses: 하위 Agent 응답 리스트 [(id, name, response), ...]

        Returns:
            str: 연결된 응답
        """
        if not sub_responses:
            return "❌ 하위 Agent로부터 응답을 받지 못했습니다."

        if len(sub_responses) == 1:
            _, name, response = sub_responses[0]
            return f"**[{name}]**\n\n{response}"

        logger.info(f"[Synthesizer] Sequentially combining {len(sub_responses)} responses")

        parts = []
        for i, (sub_id, sub_name, response) in enumerate(sub_responses, 1):
            parts.append(f"**[{i}] {sub_name}**\n\n{response}")

        return self.separator.join(parts)


class WeightedSynthesizer(ResponseSynthesizer):
    """
    가중치 기반 응답 종합 Strategy

    각 하위 Agent 응답에 가중치를 부여하여 종합합니다.
    Agent의 신뢰도, 선택 점수 등을 기반으로 가중치를 계산할 수 있습니다.

    Attributes:
        llm_client: LLM 클라이언트 인스턴스
        model: 사용할 LLM 모델명
        weight_calculator: 가중치 계산 함수
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "gpt-4o-mini",
        weight_calculator: Optional[Callable[[str, str, str], float]] = None,
    ):
        """
        Args:
            llm_client: LLM 클라이언트 (None이면 기본값 사용)
            model: LLM 모델명
            weight_calculator: (sub_id, sub_name, response) -> weight 함수
        """
        self.llm_client = llm_client or get_llm_client()
        self.model = model
        self.weight_calculator = weight_calculator or (lambda sid, name, resp: 1.0)
        
        logger.info(f"[ResponseSynthesizer] Initialized: {self.get_name()}")

    def synthesize(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """
        가중치 기반 응답 종합

        Args:
            parent_context: 상위 Agent의 검색 컨텍스트
            user_message: 사용자 질문
            sub_responses: 하위 Agent 응답 리스트 [(id, name, response), ...]

        Returns:
            str: 종합된 응답
        """
        if not sub_responses:
            return "❌ 하위 Agent로부터 응답을 받지 못했습니다."

        if len(sub_responses) == 1:
            _, name, response = sub_responses[0]
            return f"**[{name}]**\n\n{response}"

        # 가중치 계산
        weighted_responses = []
        for sub_id, sub_name, response in sub_responses:
            weight = self.weight_calculator(sub_id, sub_name, response)
            weighted_responses.append((sub_id, sub_name, response, weight))

        # 가중치 기반 정렬
        weighted_responses.sort(key=lambda x: x[3], reverse=True)

        # LLM 기반 종합
        return self._llm_weighted_synthesis(
            parent_context, user_message, weighted_responses
        )

    def _llm_weighted_synthesis(
        self,
        parent_context: str,
        user_message: str,
        weighted_responses: List[Tuple[str, str, str, float]],
    ) -> str:
        """가중치 기반 LLM 종합"""
        experts_text = "\n\n".join(
            f"### [{sub_name}] (신뢰도: {weight:.2f})\n{response.strip()}"
            for _, sub_name, response, weight in weighted_responses
        )

        system_prompt = """당신은 여러 전문가 챗봇의 응답을 가중치를 고려하여 종합하는 통합 어시스턴트입니다.

각 전문가의 응답에 신뢰도 가중치가 부여되어 있습니다.
더 높은 가중치를 가진 전문가의 의견을 우선적으로 반영하되,
다른 전문가의 중요한 포인트도 함께 고려하세요.

종합 시 다음 원칙을 따르세요:
1. 높은 가중치의 전문가 의견을 우선적으로 반영
2. 서로 다른 의견이 있다면 균형있게 다루기
3. 필요시 [전문가명] 형식으로 출처 표기
4. 가중치 정보를 사용자에게 직접 언급하지 않기

답변은 한국어로 작성하세요."""

        user_prompt = f"""**사용자 질문:**
{user_message}

**상위 Agent 검색 컨텍스트:**
{parent_context[:500] if parent_context else "(컨텍스트 없음)"}

**전문가별 응답 (신뢰도 순):**
{experts_text}

위 전문가들의 응답을 신뢰도를 고려하여 종합해주세요."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                stream=False,
            )
            
            synthesized = response.choices[0].message.content or ""
            expert_names = [f"[{name}]" for _, name, _, _ in weighted_responses]
            synthesized += "\n\n---\n**참고 전문가:** " + ", ".join(expert_names)
            
            return synthesized
            
        except Exception as e:
            logger.error(f"[Synthesizer] Weighted synthesis failed: {e}")
            # 순차 종합으로 폴백
            return SequentialSynthesizer().synthesize(
                parent_context, user_message,
                [(sid, name, resp) for sid, name, resp, _ in weighted_responses]
            )


class ChainOfThoughtSynthesizer(ResponseSynthesizer):
    """
    Chain-of-Thought 응답 종합 Strategy

    LLM이 단계별로 생각하며 응답을 종합하도록 유도합니다.
    더 논리적인 종합이 가능하지만 토큰 사용량이 증가합니다.

    Attributes:
        llm_client: LLM 클라이언트 인스턴스
        model: 사용할 LLM 모델명
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "gpt-4o",
    ):
        """
        Args:
            llm_client: LLM 클라이언트 (None이면 기본값 사용)
            model: LLM 모델명 (CoT에는 더 강력한 모델 권장)
        """
        self.llm_client = llm_client or get_llm_client()
        self.model = model
        
        logger.info(f"[ResponseSynthesizer] Initialized: {self.get_name()} (model={self.model})")

    def synthesize(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """
        Chain-of-Thought 기반 응답 종합

        Args:
            parent_context: 상위 Agent의 검색 컨텍스트
            user_message: 사용자 질문
            sub_responses: 하위 Agent 응답 리스트

        Returns:
            str: 종합된 응답
        """
        if not sub_responses:
            return "❌ 하위 Agent로부터 응답을 받지 못했습니다."

        if len(sub_responses) == 1:
            _, name, response = sub_responses[0]
            return f"**[{name}]**\n\n{response}"

        # 단계별 프롬프트 구성
        system_prompt = """당신은 여러 전문가 챗봇의 응답을 분석하고 종합하는 통합 어시스턴트입니다.

다음 단계를 따라 응답을 종합하세요:

1. **분석**: 각 전문가의 핵심 주장과 근거를 파악
2. **비교**: 전문가들의 의견을 비교하고 공통점/차이점 파악
3. **종합**: 분석과 비교를 바탕으로 하나의 일관된 답변 작성
4. **검증**: 사용자 질문의 모든 측면을 다루었는지 확인

각 단계에서 생각을 명확히 표현하세요."""

        experts_text = "\n\n".join(
            f"### [{sub_name}]\n{response.strip()}"
            for _, sub_name, response in sub_responses
        )

        user_prompt = f"""**사용자 질문:**
{user_message}

**상위 Agent 검색 컨텍스트:**
{parent_context[:500] if parent_context else "(컨텍스트 없음)"}

**전문가별 응답:**
{experts_text}

위 전문가들의 응답을 단계별로 분석하고 종합해주세요."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=3000,  # CoT는 더 많은 토큰 필요
                stream=False,
            )
            
            synthesized = response.choices[0].message.content or ""
            expert_names = [f"[{name}]" for _, name, _ in sub_responses]
            synthesized += "\n\n---\n**참고 전문가:** " + ", ".join(expert_names)
            
            return synthesized
            
        except Exception as e:
            logger.error(f"[Synthesizer] CoT synthesis failed: {e}")
            # ParallelSynthesizer로 폴백
            return ParallelSynthesizer(llm_client=self.llm_client).synthesize(
                parent_context, user_message, sub_responses
            )


def create_response_synthesizer(
    synthesizer_type: str,
    llm_client: Optional[Any] = None,
    model: str = "gpt-4o-mini",
    **kwargs,
) -> ResponseSynthesizer:
    """
    응답 종합기 팩토리 함수

    Args:
        synthesizer_type: 종합기 타입 ('parallel', 'sequential', 'weighted', 'chain_of_thought')
        llm_client: LLM 클라이언트
        model: LLM 모델명
        **kwargs: 추가 인자

    Returns:
        ResponseSynthesizer: 생성된 종합기 인스턴스

    Raises:
        ValueError: 지원하지 않는 synthesizer_type
    """
    if synthesizer_type == 'parallel':
        return ParallelSynthesizer(llm_client=llm_client, model=model, **kwargs)
    elif synthesizer_type == 'sequential':
        return SequentialSynthesizer(**kwargs)
    elif synthesizer_type == 'weighted':
        return WeightedSynthesizer(llm_client=llm_client, model=model, **kwargs)
    elif synthesizer_type == 'chain_of_thought':
        return ChainOfThoughtSynthesizer(llm_client=llm_client, model=model, **kwargs)
    else:
        raise ValueError(
            f"Unknown synthesizer_type: {synthesizer_type}. "
            "Use 'parallel', 'sequential', 'weighted', or 'chain_of_thought'."
        )
