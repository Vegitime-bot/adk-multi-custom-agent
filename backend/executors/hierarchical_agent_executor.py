from __future__ import annotations
"""
executors/hierarchical_agent_executor.py - 계층적 Agent Executor (Strategy Pattern 적용)

3-tier hierarchy 지원 + Strategy Pattern으로 위임/선택/종합 로직 분리

주요 개선사항:
- DelegationStrategy: 위임 결정 로직 추상화
- SubChatbotSelector: 하위 챗봇 선택 로직 추상화
- ResponseSynthesizer: 응답 종합 로직 추상화
- 런타임에 Strategy 교체 가능
- 단위 테스트 용이
"""
import re
import os
import logging
from dataclasses import dataclass, field
from typing import Generator, Optional, List, Tuple, Dict, Any, Literal
from concurrent.futures import ThreadPoolExecutor

from backend.core.models import ChatbotDef, ExecutionRole, Message
from backend.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from backend.executors.agent_executor import AgentExecutor
from backend.executors.strategies import (
    DelegationStrategy,
    ConfidenceThresholdStrategy,
    DelegateResult,
    SubChatbotSelector,
    HybridSelector,
    ResponseSynthesizer,
    ParallelSynthesizer,
    SequentialSynthesizer,
)
from backend.managers.memory_manager import MemoryManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.services.embedding_service import get_embedding_service
from backend.llm.client import get_llm_client

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 위임용 Circuit Breaker 기본 설정 - config에서 값을 로드하는 팩토리 함수
def get_delegation_cb_config() -> CircuitBreakerConfig:
    """설정에서 Circuit Breaker 설정 로드"""
    return CircuitBreakerConfig(
        failure_threshold=None,  # config에서 로드
        recovery_timeout=None,   # config에서 로드
        half_open_max_calls=1,
        success_threshold=1,
    )


# 모듈 레벨에서 지연 로드를 위한 전역 변수
_DELEGATION_CB_CONFIG = None

def get_delegation_config() -> CircuitBreakerConfig:
    """Circuit Breaker 설정 반환 (싱글턴)"""
    global _DELEGATION_CB_CONFIG
    if _DELEGATION_CB_CONFIG is None:
        _DELEGATION_CB_CONFIG = get_delegation_cb_config()
    return _DELEGATION_CB_CONFIG


def get_hybrid_score_threshold() -> float:
    """환경변수에서 HYBRID_SCORE_THRESHOLD 값을 가져옴 (기본값: 0.15)"""
    return float(os.getenv('HYBRID_SCORE_THRESHOLD', '0.15'))


class HierarchicalAgentExecutor(AgentExecutor):
    """
    계층적 Agent Executor (Strategy Pattern 적용)

    실행 흐름:
    1. 자체 DB로 답변 시도
    2. 검색 결과 기반 Confidence 계산
    3. DelegationStrategy로 위임 결정
    4. SubChatbotSelector로 하위 Agent 선택
    5. ResponseSynthesizer로 응답 종합

    Strategy 주입:
    - delegation_strategy: 위임 결정 전략
    - sub_chatbot_selector: 하위 챗봇 선택 전략
    - response_synthesizer: 응답 종합 전략
    """

    # 레거시 키워드 매핑 (하위 호환)
    KEYWORDS_MAP = HybridSelector.KEYWORDS_MAP

    # 위임 관련 상수 - config에서 동적으로 로드
    DEFAULT_DELEGATION_THRESHOLD = 70
    MAX_DELEGATION_DEPTH = None  # config에서 동적 로드

    @classmethod
    def _get_max_delegation_depth(cls) -> int:
        """설정에서 최대 위임 깊이 로드"""
        try:
            from config import settings
            return settings.MAX_DELEGATION_DEPTH
        except (ImportError, AttributeError):
            return 5  # 폴백 기본값

    def _get_max_depth(self) -> int:
        """인스턴스에서 최대 위임 깊이 가져오기"""
        if self.MAX_DELEGATION_DEPTH is not None:
            return self.MAX_DELEGATION_DEPTH
        return self._get_max_delegation_depth()

    def __init__(
        self,
        chatbot_def: ChatbotDef,
        ingestion_client: IngestionClient,
        memory_manager: MemoryManager,
        chatbot_manager=None,
        accumulated_context: str = "",
        delegation_depth: int = 0,
        # Strategy 주입 (DI)
        delegation_strategy: Optional[DelegationStrategy] = None,
        sub_chatbot_selector: Optional[SubChatbotSelector] = None,
        response_synthesizer: Optional[ResponseSynthesizer] = None,
    ):
        super().__init__(chatbot_def, ingestion_client, memory_manager)
        self.chatbot_manager = chatbot_manager
        self.accumulated_context = accumulated_context
        self.delegation_depth = delegation_depth

        # Policy 설정
        self.delegation_threshold = chatbot_def.policy.get(
            'delegation_threshold', self.DEFAULT_DELEGATION_THRESHOLD
        )
        self.multi_sub_execution = chatbot_def.policy.get('multi_sub_execution', False)
        self.max_parallel_subs = chatbot_def.policy.get('max_parallel_subs', 3) or 3
        self.synthesis_mode = chatbot_def.policy.get('synthesis_mode', 'parallel')
        self.hybrid_score_threshold = chatbot_def.policy.get(
            'hybrid_score_threshold', get_hybrid_score_threshold()
        )
        self.enable_parent_delegation = chatbot_def.policy.get(
            'enable_parent_delegation', True
        )

        # Strategy 초기화 (주입되지 않으면 기본값 사용)
        self._delegation_strategy = delegation_strategy
        self._sub_chatbot_selector = sub_chatbot_selector
        self._response_synthesizer = response_synthesizer
        
        # Strategy가 주입되지 않았으면 Policy 기반으로 생성
        self._init_strategies()

        self._embedding_service = get_embedding_service()

    def _init_strategies(self) -> None:
        """Policy 설정을 기반으로 Strategy 초기화"""
        # 1. DelegationStrategy
        if self._delegation_strategy is None:
            strategy_type = self.chatbot_def.policy.get('delegation_strategy_type', 'confidence')
            if strategy_type == 'confidence':
                self._delegation_strategy = ConfidenceThresholdStrategy(
                    threshold=self.delegation_threshold
                )
            else:
                # 기본값
                self._delegation_strategy = ConfidenceThresholdStrategy(
                    threshold=self.delegation_threshold
                )
            logger.info(f"[Strategy] Initialized DelegationStrategy: {self._delegation_strategy.get_name()}")

        # 2. SubChatbotSelector
        if self._sub_chatbot_selector is None:
            selector_type = self.chatbot_def.policy.get('sub_chatbot_selector_type', 'hybrid')
            if selector_type == 'hybrid':
                self._sub_chatbot_selector = HybridSelector(
                    threshold=self.hybrid_score_threshold
                )
            elif selector_type == 'keyword':
                from backend.executors.strategies import KeywordOnlySelector
                self._sub_chatbot_selector = KeywordOnlySelector()
            else:
                self._sub_chatbot_selector = HybridSelector(
                    threshold=self.hybrid_score_threshold
                )
            logger.info(f"[Strategy] Initialized SubChatbotSelector: {self._sub_chatbot_selector.get_name()}")

        # 3. ResponseSynthesizer
        if self._response_synthesizer is None:
            synthesizer_type = self.chatbot_def.policy.get('synthesis_mode', 'parallel')
            if synthesizer_type == 'sequential':
                self._response_synthesizer = SequentialSynthesizer()
            else:  # parallel
                self._response_synthesizer = ParallelSynthesizer()
            logger.info(f"[Strategy] Initialized ResponseSynthesizer: {self._response_synthesizer.get_name()}")

    # ====================================================================
    # Strategy 주입/교체 메서드 (런타임 전략 교체용)
    # ====================================================================

    def set_delegation_strategy(self, strategy: DelegationStrategy) -> None:
        """런타임에 DelegationStrategy 교체"""
        self._delegation_strategy = strategy
        logger.info(f"[Strategy] DelegationStrategy changed to: {strategy.get_name()}")

    def set_sub_chatbot_selector(self, selector: SubChatbotSelector) -> None:
        """런타임에 SubChatbotSelector 교체"""
        self._sub_chatbot_selector = selector
        logger.info(f"[Strategy] SubChatbotSelector changed to: {selector.get_name()}")

    def set_response_synthesizer(self, synthesizer: ResponseSynthesizer) -> None:
        """런타임에 ResponseSynthesizer 교체"""
        self._response_synthesizer = synthesizer
        logger.info(f"[Strategy] ResponseSynthesizer changed to: {synthesizer.get_name()}")

    # ====================================================================
    # 메인 실행 메서드
    # ====================================================================

    def execute(
        self,
        message: str,
        session_id: str,
    ) -> Generator[str, None, None]:
        """
        계층적 Agent 실행 (Strategy Pattern 적용)

        Phase 1: 자체 답변 시도 (RAG 검색 + Confidence 계산)
        Phase 2: 위임 결정 (DelegationStrategy)
        Phase 3: 위임 실행 또는 직접 응답
        """
        logger.info(f"[EXECUTE] {self.chatbot_def.name}(L{self.chatbot_def.level}) | msg: {message[:50]}... | depth: {self.delegation_depth}")

        # 위임 깊이 초과 체크
        max_depth = self._get_max_depth()
        if self.delegation_depth >= max_depth:
            logger.warning(f"[EXECUTE] Max delegation depth exceeded: {self.delegation_depth}")
            yield f"⚠️ 최대 위임 깊이({max_depth})를 초과했습니다.\n\n"
            yield from self._execute_with_context(message, session_id, "")
            return

        # Phase 0: 히스토리 압축
        history_context = ""
        if session_id and self.memory:
            history = self.memory.get_history(self.chatbot_def.id, session_id)
            if history:
                history_context = self._compact_history(history)

        # Phase 1: RAG 검색
        context = self._retrieve(message, self.chatbot_def.retrieval.db_ids)

        # Phase 2: 컨텍스트 결합
        combined_context = self._combine_contexts(self.accumulated_context, context)
        if history_context:
            combined_context = f"## 이전 대화 컨텍스트\n{history_context}\n\n---\n\n{combined_context}"

        confidence = self._calculate_confidence(combined_context, message)

        # Phase 3: 위임 결정 (Strategy 사용)
        delegate = self._delegation_strategy.decide(
            confidence=confidence,
            has_sub_chatbots=bool(self.chatbot_def.sub_chatbots),
            message=message,
        )
        logger.info(f"[DELEGATION] {self.chatbot_def.name} → {delegate.target.upper()} | conf: {confidence}% | reason: {delegate.reason}")

        # Phase 4: 위임 실행
        if delegate.target == 'self':
            yield from self._respond_directly_with_retry(message, session_id, combined_context, confidence)
        elif delegate.target == 'sub':
            yield from self._delegate(message, session_id, combined_context, confidence)
        else:
            yield from self._respond_uncertain(message, session_id, combined_context, confidence)

    # ====================================================================
    # 위임 실행
    # ====================================================================

    def _delegate(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """위임 실행"""
        logger.info(f"[DELEGATE] {self.chatbot_def.name} -> sub | confidence: {confidence}%")

        yield f"📋 이 질문은 전문가 상담이 필요합니다.\n\n"
        yield f"({self.chatbot_def.name} 신뢰도: {confidence}% → 하위 Agent 위임)\n\n"
        yield f"---\n📡 **전문가 챗봇을 호출합니다...**\n\n"

        if self.multi_sub_execution:
            yield from self._delegate_to_multi_subs(message, session_id, confidence)
        else:
            yield from self._delegate_to_single_sub(message, session_id, confidence)

    def _delegate_to_multi_subs(
        self,
        message: str,
        session_id: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """다중 하위 Agent 선택 및 실행 (SubChatbotSelector 사용)"""
        sub_candidates = self._sub_chatbot_selector.select(
            message=message,
            sub_chatbot_refs=self.chatbot_def.sub_chatbots,
            chatbot_manager=self.chatbot_manager,
            embedding_service=self._embedding_service,
            max_results=self.max_parallel_subs,
        )

        if not sub_candidates:
            yield from self._fallback_to_self(message, session_id, confidence,
                                                 reason="적합한 하위 Agent를 찾을 수 없습니다")
            return

        yield f"**선택된 전문가**: {', '.join([c[0].name for c in sub_candidates])}\n\n"

        # 하위 Agent 실행
        sub_responses = self._execute_multiple_subs(sub_candidates, message, session_id)

        if sub_responses:
            yield "\n---\n🔄 **응답을 종합하는 중입니다...**\n\n"
            synthesized = self._response_synthesizer.synthesize(
                parent_context="",
                user_message=message,
                sub_responses=sub_responses,
            )
            yield synthesized
        else:
            yield from self._fallback_to_self(message, session_id, confidence,
                                                 reason="하위 Agent들이 응답할 수 없습니다")

    def _delegate_to_single_sub(
        self,
        message: str,
        session_id: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """단일 하위 Agent 선택 및 실행 (SubChatbotSelector 사용)"""
        candidates = self._sub_chatbot_selector.select(
            message=message,
            sub_chatbot_refs=self.chatbot_def.sub_chatbots,
            chatbot_manager=self.chatbot_manager,
            embedding_service=self._embedding_service,
            max_results=1,
        )

        if candidates:
            sub_chatbot, selection_info, scores = candidates[0]
            logger.info(f"[DELEGATE] Selected sub: {sub_chatbot.name} {selection_info}")

            # 선택 근거 표시
            yield "📊 **하위 후보 점수(상위 3)**\n"
            for i, (cb, info, sc) in enumerate(candidates[:3], 1):
                yield f"{i}. {cb.name} (id={cb.id}) → {info}\n"
            yield "\n"

            yield f"✅ **선택된 하위 챗봇: [{sub_chatbot.name}]** {selection_info}\n\n"
            yield from self._delegate_to_sub(sub_chatbot, message, session_id, "")
        else:
            yield from self._fallback_to_self(message, session_id, confidence,
                                                 reason="적합한 하위 Agent를 찾을 수 없습니다")

    def _delegate_to_sub(
        self,
        sub_chatbot: ChatbotDef,
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> Generator[str, None, None]:
        """하위 Agent에게 위임 실행 (Circuit Breaker 보호)"""
        cb = self._get_circuit_breaker(sub_chatbot.id)

        if cb.state.value == 'open':
            stats = cb.stats
            logger.warning(f"[CIRCUIT_BREAKER] {sub_chatbot.name} is OPEN")
            yield f"⚠️ **[{sub_chatbot.name}] 서비스 일시 중단**\n\n"
            yield f"현재 '{sub_chatbot.name}' 서비스가 일시적으로 사용 불가능합니다.\n"
            yield f"(원인: 연속 실패로 인한 서비스 보호, 거부 횟수: {stats.total_rejections}회)\n\n"
            yield "잠시 후 다시 시도해 주세요.\n"
            return

        # 하위 Executor 생성 (Strategy 전달)
        sub_executor = HierarchicalAgentExecutor(
            chatbot_def=sub_chatbot,
            ingestion_client=self.ingestion,
            memory_manager=self.memory,
            chatbot_manager=self.chatbot_manager,
            accumulated_context="",
            delegation_depth=self.delegation_depth + 1,
            # Strategy 상속 (같은 Strategy 사용)
            delegation_strategy=self._delegation_strategy,
            sub_chatbot_selector=self._sub_chatbot_selector,
            response_synthesizer=self._response_synthesizer,
        )

        enhanced_message = message
        if parent_context:
            enhanced_message = f"[상위 Agent 컨텍스트] {parent_context[:500]}...\n\n[질문] {message}"

        yield f"🧾 {self._source_note(sub_chatbot)}\n\n"

        try:
            for chunk in sub_executor.execute(enhanced_message, session_id):
                yield chunk
            cb._on_success()
        except Exception as e:
            cb._on_failure()
            logger.error(f"[CIRCUIT_BREAKER] {sub_chatbot.name} execution failed: {e}")
            yield f"\n❌ 하위 Agent '{sub_chatbot.name}' 실행 중 오류 발생: {str(e)}\n"

    # ====================================================================
    # 다중 하위 Agent 실행
    # ====================================================================

    def _execute_multiple_subs(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, Dict[str, float]]],
        message: str,
        session_id: str,
    ) -> List[Tuple[str, str, str]]:
        """다중 하위 Agent 실행 (SynthesisMode에 따라 병렬/순차)"""
        if self.synthesis_mode == 'sequential':
            return self._execute_multiple_subs_sequential(sub_candidates, message, session_id)
        return self._execute_multiple_subs_parallel(sub_candidates, message, session_id)

    def _execute_multiple_subs_sequential(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, Dict[str, float]]],
        message: str,
        session_id: str,
    ) -> List[Tuple[str, str, str]]:
        """순차적으로 다중 하위 Agent 실행"""
        results = []
        for sub_chatbot, selection_info, scores in sub_candidates:
            try:
                response = self._execute_single_sub(sub_chatbot, message, session_id, "")
                if response:
                    results.append((sub_chatbot.id, sub_chatbot.name, response))
            except Exception as e:
                logger.warning(f"[DELEGATE] {sub_chatbot.name} error: {e}")
                results.append((sub_chatbot.id, sub_chatbot.name, f"[오류: 응답 생성 실패 - {str(e)}]"))
        return results

    def _execute_multiple_subs_parallel(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, Dict[str, float]]],
        message: str,
        session_id: str,
    ) -> List[Tuple[str, str, str]]:
        """병렬로 다중 하위 Agent 실행"""
        results = []
        errors = []

        def execute_single(sub_chatbot: ChatbotDef) -> Tuple[str, str, Optional[str]]:
            try:
                response = self._execute_single_sub(sub_chatbot, message, session_id, "")
                return (sub_chatbot.id, sub_chatbot.name, response)
            except Exception as e:
                logger.warning(f"[DELEGATE] {sub_chatbot.name} error: {e}")
                return (sub_chatbot.id, sub_chatbot.name, None)

        with ThreadPoolExecutor(max_workers=min(len(sub_candidates), 5)) as executor:
            future_to_sub = {executor.submit(execute_single, sub[0]): sub for sub in sub_candidates}
            for future in future_to_sub:
                sub_id, sub_name, response = future.result()
                if response:
                    results.append((sub_id, sub_name, response))
                else:
                    errors.append((sub_id, sub_name))

        if errors:
            logger.warning(f"[DELEGATE] Failed sub-agents: {errors}")

        return results

    def _execute_single_sub(
        self,
        sub_chatbot: ChatbotDef,
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> str:
        """단일 하위 Agent 실행 (Circuit Breaker 보호)"""
        logger.info(f"[DELEGATE] Executing sub: {sub_chatbot.name}(L{sub_chatbot.level})")

        cb = self._get_circuit_breaker(sub_chatbot.id)

        def _execute_sub():
            sub_executor = HierarchicalAgentExecutor(
                sub_chatbot,
                self.ingestion,
                self.memory,
                self.chatbot_manager,
                accumulated_context="",
                delegation_depth=self.delegation_depth + 1,
                delegation_strategy=self._delegation_strategy,
                sub_chatbot_selector=self._sub_chatbot_selector,
                response_synthesizer=self._response_synthesizer,
            )
            enhanced_message = message
            if parent_context:
                enhanced_message = f"[상위 Agent 컨텍스트] {parent_context[:500]}...\n\n[질문] {message}"

            sub_answer = "".join(sub_executor.execute(enhanced_message, session_id))
            source_header = f"🧾 {self._source_note(sub_chatbot)}\n\n"
            return source_header + sub_answer

        def _fallback():
            stats = cb.stats
            return (
                f"⚠️ **[{sub_chatbot.name}] 서비스 일시 중단**\n\n"
                f"현재 '{sub_chatbot.name}' 서비스가 일시적으로 사용 불가능합니다.\n"
                f"(원인: 연속 실패로 인한 서비스 보호)\n\n"
                f"잠시 후 다시 시도해 주세요."
            )

        try:
            return cb.call(_execute_sub, _fallback)
        except Exception as e:
            logger.error(f"[DELEGATE] Error executing sub {sub_chatbot.name}: {e}")
            return f"❌ 하위 Agent '{sub_chatbot.name}' 실행 중 오류 발생: {str(e)}"

    # ====================================================================
    # 직접 응답 / Fallback
    # ====================================================================

    def _respond_directly_with_retry(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """Confidence 충분 - 자체 답변"""
        logger.info(f"[RESPOND] {self.chatbot_def.name} trying direct response (confidence: {confidence}%)")

        yield f"📢 **[{self.chatbot_def.name}]** (신뢰도: {confidence}% / Level: {self.chatbot_def.level})\n"
        yield f"🧾 {self._source_note(self.chatbot_def)}\n\n"

        answer_parts = []
        for part in self._execute_with_context(message, session_id, context):
            answer_parts.append(part)
            yield part

        answer = "".join(answer_parts)

        # 품질 검증
        original_question = message
        if "[질문]" in message:
            original_question = message.split("[질문]")[-1].strip()

        quality_score = self._evaluate_answer_quality(answer, original_question)

        if quality_score >= 0.3:
            return

        # 품질 낮음 → 하위로 재위임
        logger.info(f"[RESPOND] {self.chatbot_def.name} quality low, attempting re-delegation")
        yield f"\n\n⚠️ 답변 품질이 낮아 하위 Agent로 재위임합니다...\n\n"

        if self.chatbot_def.sub_chatbots:
            yield from self._delegate(message, session_id, context, confidence)
        else:
            yield "❌ 하위 Agent가 없어 재위임할 수 없습니다.\n"

    def _respond_uncertain(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """위임 대상 없음 - 최선의 답변 제공 (Fallback)"""
        yield f"📢 **[{self.chatbot_def.name}]** (최종 답변 / 신뢰도: {confidence}% / Level: {self.chatbot_def.level})\n"
        yield f"🧾 {self._source_note(self.chatbot_def)}\n\n"
        if self.accumulated_context:
            yield "*(하위 Agent들의 컨텍스트를 종합하여 답변합니다)*\n\n"
        yield from self._execute_with_context(message, session_id, context)

    def _fallback_to_self(
        self,
        message: str,
        session_id: str,
        confidence: float,
        reason: str = "",
    ) -> Generator[str, None, None]:
        """하위 위임 실패 시 자체 응답으로 Fallback"""
        logger.info(f"[DELEGATE] Falling back to self: {reason}")
        yield f"❌ {reason}.\n"
        context = self._combine_contexts(self.accumulated_context, "")
        yield from self._execute_with_context(message, session_id, context)

    # ====================================================================
    # 헬퍼 메서드
    # ====================================================================

    def _source_note(self, chatbot: ChatbotDef) -> str:
        """응답 출처 표기 문자열 생성"""
        db_ids = getattr(chatbot.retrieval, 'db_ids', []) if hasattr(chatbot, 'retrieval') else []
        db_text = ', '.join(db_ids) if db_ids else '(없음)'
        return f"출처: {chatbot.name} (id={chatbot.id}, level={chatbot.level}, db={db_text})"

    def _combine_contexts(self, accumulated: str, current: str) -> str:
        """누적된 컨텍스트와 현재 컨텍스트를 결합"""
        if not accumulated:
            return current
        if not current:
            return accumulated
        return f"[상위 컨텍스트]\n{accumulated}\n\n[현재 검색 결과]\n{current}"

    def _execute_with_context(
        self,
        message: str,
        session_id: str,
        context: str,
    ) -> Generator[str, None, None]:
        """주어진 컨텍스트로 Agent 실행"""
        history = self.memory.get_history(self.chatbot_def.id, session_id)

        messages = self._build_messages_with_history(
            system_prompt=self.chatbot_def.system_prompt,
            history=history,
            user_message=message,
            context=context,
        )

        full_response = []
        for chunk in self._stream_chat(messages):
            full_response.append(chunk)
            yield chunk

        self.memory.append_pair(
            chatbot_id=self.chatbot_def.id,
            session_id=session_id,
            user_content=message,
            assistant_content="".join(full_response),
            max_messages=self.chatbot_def.memory.max_messages,
        )

    def _evaluate_answer_quality(self, answer: str, question: str) -> float:
        """답변 품질 평가 (0.0 ~ 1.0)"""
        if not answer or len(answer.strip()) < 10:
            return 0.0

        # 부정 표현 체크
        negative_patterns = [
            r'모르겠', r'없습니다', r'없어요', r'찾을 수 없', r'정보가 없',
            r'답변할 수 없', r'확인할 수 없', r'제공할 수 없',
            r'해당 정보', r'관련 정보', r'문의하세요', r'문의 주세요',
        ]
        answer_lower = answer.lower()
        negative_count = sum(1 for p in negative_patterns if re.search(p, answer_lower))

        if negative_count >= 2:
            return 0.1
        if negative_count >= 1:
            return 0.2

        # 키워드 오버랩
        question_words = set(re.findall(r'\b\w{2,}\b', question.lower()))
        answer_words = set(re.findall(r'\b\w{2,}\b', answer_lower))
        overlap = len(question_words & answer_words)
        overlap_ratio = overlap / max(len(question_words), 1)

        base_score = 0.4
        keyword_bonus = min(overlap_ratio * 0.4, 0.4)

        return min(base_score + keyword_bonus, 1.0)
