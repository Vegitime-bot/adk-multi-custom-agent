from __future__ import annotations
"""
executors/hierarchical_agent_executor.py - 계층적 Agent Executor (3-tier hierarchy 지원)

계층 구조에서 상위로 위임하는 기능 추가:
- Confidence 기반 위임 결정
- 상위 Agent로 위임 (현재 Agent가 답변할 수 없는 경우)
- Context 누적 (상위로 전달)
- Root에서 최종 합성

기존 parent_agent_executor.py 기능 확장
"""
import re
import asyncio
import os
import logging
from dataclasses import dataclass, field
from typing import Generator, Optional, List, Tuple, Dict, Any, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.core.models import ChatbotDef, ExecutionRole, Message
from backend.executors.agent_executor import AgentExecutor
from backend.managers.memory_manager import MemoryManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.services.embedding_service import get_embedding_service
from backend.llm.client import get_llm_client

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_hybrid_score_threshold() -> float:
    """환경변수에서 HYBRID_SCORE_THRESHOLD 값을 가져옴 (기본값: 0.15)"""
    return float(os.getenv('HYBRID_SCORE_THRESHOLD', '0.15'))


@dataclass
class DelegateResult:
    """위임 결정 결과"""
    target: Literal['self', 'sub', 'parent', 'fallback']
    reason: str = ""


class HierarchicalAgentExecutor(AgentExecutor):
    """
    계층적 Agent Executor (3-tier hierarchy 지원)

    실행 흐름:
    1. 자체 DB로 답변 시도
    2. 검색 결과 기반 Confidence 계산
    3. Confidence < threshold:
       - 하위 Agent 있으면 하위로 위임 (기존 동작)
       - 하위 Agent 없거나 실패:
         - 부모 있으면 부모로 위임 (신규)
         - 부모 없으면 (Root) 실패 처리 또는 sub_chatbots 시도
    4. Context 누적 및 상위 전달
    5. Root에서 최종 합성

    위임 체인:
    User Query
       ↓
    Current Agent (Level 2 - Child)
       ↓ (low confidence)
    Delegate to Parent (Level 1)
       ↓ (still low confidence)
    Delegate to Grand-Parent (Level 0 - Root)
       ↓
    Root synthesizes final response
    """

    # 키워드 기반 매칭 (하위 호환 유지)
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

    # 하이브리드 가중치 (keyword : embedding)
    KEYWORD_WEIGHT = 0.4
    EMBEDDING_WEIGHT = 0.6

    # 하이브리드 스코어 임계값 (이 값 이상인 후보만 선택)
    # 환경변수 HYBRID_SCORE_THRESHOLD로 오버라이드 가능
    HYBRID_SCORE_THRESHOLD = get_hybrid_score_threshold()

    # 위임 관련 상수
    DEFAULT_DELEGATION_THRESHOLD = 70
    MAX_DELEGATION_DEPTH = 5  # 최대 위임 깊이

    def __init__(
        self,
        chatbot_def: ChatbotDef,
        ingestion_client: IngestionClient,
        memory_manager: MemoryManager,
        chatbot_manager=None,
        accumulated_context: str = "",
        delegation_depth: int = 0,
    ):
        super().__init__(chatbot_def, ingestion_client, memory_manager)
        self.chatbot_manager = chatbot_manager
        self.accumulated_context = accumulated_context  # 상위에서 전달된 컨텍스트
        self.delegation_depth = delegation_depth  # 현재 위임 깊이 (순환 방지)

        # Policy 설정
        self.delegation_threshold = chatbot_def.policy.get(
            'delegation_threshold', self.DEFAULT_DELEGATION_THRESHOLD
        )
        self.multi_sub_execution = chatbot_def.policy.get('multi_sub_execution', False)
        self.max_parallel_subs = chatbot_def.policy.get('max_parallel_subs', 3) or 3  # 0이면 기본값 3 사용
        self.synthesis_mode = chatbot_def.policy.get('synthesis_mode', 'parallel')
        self.hybrid_score_threshold = chatbot_def.policy.get(
            'hybrid_score_threshold',
            get_hybrid_score_threshold()  # fallback to env/default
        )
        self.enable_parent_delegation = chatbot_def.policy.get(
            'enable_parent_delegation', True
        )  # 상위 위임 활성화 여부

        self._embedding_service = get_embedding_service()

    def execute(
        self,
        message: str,
        session_id: str,
    ) -> Generator[str, None, None]:
        """
        계층적 Agent 실행

        Phase 1: 자체 답변 시도 (RAG 검색 + Confidence 계산)
        Phase 2: 위임 결정 및 실행 (_select_delegate_target → _delegate or _respond_directly)
        Phase 3: Fallback 처리 (_respond_uncertain)
        """
        # 위임 관련 핵심 로그만 남김
        logger.info(f"[EXECUTE] {self.chatbot_def.name}(L{self.chatbot_def.level}) | msg: {message[:50]}... | depth: {self.delegation_depth}")

        # 위임 깊이 초과 체크
        if self.delegation_depth >= self.MAX_DELEGATION_DEPTH:
            logger.warning(f"[EXECUTE] Max delegation depth exceeded: {self.delegation_depth}")
            yield f"⚠️ 최대 위임 깊이({self.MAX_DELEGATION_DEPTH})를 초과했습니다.\n\n"
            yield from self._execute_with_context(message, session_id, "")
            return

        # Phase 0: 히스토리 압축 (검색 쿼리 확장 대신 컨텍스트에 prepend)
        history_context = ""
        if session_id and self.memory:
            history = self.memory.get_history(self.chatbot_def.id, session_id)
            if history:
                history_context = self._compact_history(history)
                if history_context:
                    logger.info(f"[EXECUTE] History compacted: {len(history_context)} chars")

        # Phase 1: RAG 검색 (원본 메시지로 검색)
        context = self._retrieve(message, self.chatbot_def.retrieval.db_ids)
        
        # Phase 2: 히스토리를 검색 컨텍스트에 prepend
        combined_context = self._combine_contexts(self.accumulated_context, context)
        if history_context:
            combined_context = f"## 이전 대화 컨텍스트\n{history_context}\n\n---\n\n{combined_context}"
            logger.info(f"[EXECUTE] History prepended to context")
        
        confidence = self._calculate_confidence(combined_context, message)

        # Phase 3: 위임 결정 및 실행
        delegate = self._select_delegate_target(confidence, message)
        logger.info(f"[DELEGATION] {self.chatbot_def.name} → {delegate.target.upper()} | conf: {confidence}% | reason: {delegate.reason}")

        if delegate.target == 'self':
            yield from self._respond_directly_with_retry(message, session_id, combined_context, confidence)
        elif delegate.target == 'sub':
            yield from self._delegate(message, session_id, combined_context, confidence, delegate)
        else:
            # Phase 4: Fallback
            yield from self._respond_uncertain(message, session_id, combined_context, confidence)

    # ====================================================================
    # Phase 2: 위임 결정
    # ====================================================================

    def _select_delegate_target(self, confidence: float, message: str) -> DelegateResult:
        """
        하향 위임만 지원하는 단순화된 버전
        """
        if confidence >= self.delegation_threshold:
            # Confidence 충분하면 자체 답변
            return DelegateResult(
                target='self',
                reason=f"confidence {confidence}% >= threshold {self.delegation_threshold}%",
            )
        
        # Confidence 부족하면 하위로 위임 시도
        if self.chatbot_def.sub_chatbots:
            return DelegateResult(
                target='sub',
                reason=f"confidence {confidence}% < threshold, has sub_chatbots",
            )
        
        # Leaf 노드면 fallback
        return DelegateResult(
            target='fallback',
            reason=f"confidence {confidence}% < threshold, no sub_chatbots",
        )

    def _delegate(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
        delegate: DelegateResult,
    ) -> Generator[str, None, None]:
        """위임 실행 - sub 또는 fallback으로 라우팅 (상위 위임 제거)"""
        if delegate.target == 'sub':
            # 위임 시 context는 비우고, 하위 Agent가 자체 DB로 검색하게 함
            yield from self._delegate_to_sub_chatbots(message, session_id, "", confidence)
        else:
            # fallback: 하위가 없으면 현재 Agent로 답변
            yield from self._respond_uncertain(message, session_id, context, confidence)

    def _source_note(self, chatbot: ChatbotDef) -> str:
        """응답 출처 표기 문자열 생성"""
        db_ids = getattr(chatbot.retrieval, 'db_ids', []) if hasattr(chatbot, 'retrieval') else []
        db_text = ', '.join(db_ids) if db_ids else '(없음)'
        return f"출처: {chatbot.name} (id={chatbot.id}, level={chatbot.level}, db={db_text})"

    # ====================================================================
    # Phase 2a/2b: 직접 응답 / 불확실 응답
    # ====================================================================

    def _respond_directly_with_retry(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """Confidence 충분 - 자체 답변 (품질 검증 및 재위임 지원)"""
        logger.info(f"[RESPOND] {self.chatbot_def.name} trying direct response (confidence: {confidence}%)")
        
        # 1차 시도: 자체 답변 생성
        yield f"📢 **[{self.chatbot_def.name}]** (신뢰도: {confidence}% / Level: {self.chatbot_def.level})\n"
        yield f"🧾 {self._source_note(self.chatbot_def)}\n\n"
        
        # 답변 생성
        answer_parts = []
        for part in self._execute_with_context(message, session_id, context):
            answer_parts.append(part)
            yield part
        
        answer = "".join(answer_parts)
        
        # 원래 질문 추출 (컨텍스트 제거)
        original_question = message
        if "[질문]" in message:
            original_question = message.split("[질문]")[-1].strip()
        
        # 품질 검증 (원래 질문 기준)
        quality_score = self._evaluate_answer_quality(answer, original_question)
        # DEBUG: logger.info(f"[RESPOND] {self.chatbot_def.name} quality score: {quality_score} (question: {original_question[:30]}...)")
        
        if quality_score >= 0.3:  # 품질 임계값
            # DEBUG: logger.info(f"[RESPOND] {self.chatbot_def.name} answer quality OK")
            return
        
        # ❌ 품질 낮음 → 하위로 재위임 시도
        logger.info(f"[RESPOND] {self.chatbot_def.name} quality low, attempting re-delegation to sub")
        yield f"\n\n⚠️ 답변 품질이 낮아 하위 Agent로 재위임합니다...\n\n"
        
        if self.chatbot_def.sub_chatbots:
            yield from self._delegate_to_sub_chatbots(message, session_id, context, confidence)
        else:
            yield "❌ 하위 Agent가 없어 재위임할 수 없습니다.\n"

    def _evaluate_answer_quality(self, answer: str, question: str) -> float:
        """답변 품질 평가 (0.0 ~ 1.0)"""
        if not answer or len(answer.strip()) < 10:
            return 0.0  # 빈 답변 또는 너무 짧음
        
        # "모르겠다", "없다" 등의 부정 표현 체크
        negative_patterns = [
            r'모르겠', r'없습니다', r'없어요', r'찾을 수 없', r'정보가 없',
            r'답변할 수 없', r'확인할 수 없', r'제공할 수 없',
            r'해당 정보', r'관련 정보', r'문의하세요', r'문의 주세요',
        ]
        answer_lower = answer.lower()
        negative_count = sum(1 for p in negative_patterns if re.search(p, answer_lower))
        
        if negative_count >= 2:
            return 0.1  # 부정 표현 다수
        if negative_count >= 1:
            return 0.2  # 부정 표현 1개
        
        # 질문의 키워드가 답변에 포함되어 있는지 체크
        question_words = set(re.findall(r'\b\w{2,}\b', question.lower()))
        answer_words = set(re.findall(r'\b\w{2,}\b', answer_lower))
        overlap = len(question_words & answer_words)
        overlap_ratio = overlap / max(len(question_words), 1)
        
        # 기본 점수 + 키워드 오버랩
        base_score = 0.4
        keyword_bonus = min(overlap_ratio * 0.4, 0.4)
        
        return min(base_score + keyword_bonus, 1.0)

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

    # ====================================================================
    # 하위 Agent 위임
    # ====================================================================

    def _delegate_to_sub_chatbots(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """하위 챗봇으로 위임"""
        logger.info(f"[DELEGATE] {self.chatbot_def.name} -> sub | confidence: {confidence}% | subs: {[s.id for s in self.chatbot_def.sub_chatbots]}")

        yield f"📋 이 질문은 전문가 상담이 필요합니다.\n\n"
        yield f"({self.chatbot_def.name} 신뢰도: {confidence}% → 하위 Agent 위임)\n\n"
        yield f"---\n📡 **전문가 챗봇을 호출합니다...**\n\n"

        if self.multi_sub_execution:
            yield from self._delegate_to_multi_subs(message, session_id, context, confidence)
        else:
            yield from self._delegate_to_single_sub(message, session_id, context, confidence)

    def _delegate_to_multi_subs(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """다중 하위 Agent 선택 및 실행"""
        sub_candidates = self._select_sub_chatbot_hybrid_multi(message)
        # DEBUG: logger.info(f"[DELEGATE DEBUG] _delegate_to_multi_subs: candidates={len(sub_candidates)}")
        
        if not sub_candidates:
            # DEBUG: logger.info("[DELEGATE] No multi-sub candidates found, falling back")
            yield from self._fallback_to_parent_or_self(message, session_id, context, confidence,
                                                         reason="적합한 하위 Agent를 찾을 수 없습니다")
            return

        yield f"**선택된 전문가**: {', '.join([c[0].name for c in sub_candidates])}\n\n"
        # 위임 시 context는 비우고, 하위 Agent가 자체 DB로 검색하게 함
        sub_responses = self._execute_multiple_subs(sub_candidates, message, session_id, "")

        if sub_responses:
            yield "\n---\n🔄 **응답을 종합하는 중입니다...**\n\n"
            synthesized = self._synthesize_responses(
                parent_context="",  # context 비움
                user_message=message,
                sub_responses=sub_responses,
            )
            yield synthesized
        else:
            yield from self._fallback_to_parent_or_self(message, session_id, "", confidence,
                                                         reason="하위 Agent들이 응답할 수 없습니다")

    def _delegate_to_single_sub(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """단일 하위 Agent 선택 및 실행"""
        # DEBUG: logger.info(f"[DELEGATE DEBUG] _delegate_to_single_sub called with message: '{message[:50]}...'")
        candidates = self._select_sub_chatbot_hybrid_multi(message)
        # DEBUG: logger.debug(f"[DELEGATE] Single-sub candidates: {len(candidates)}")
        
        if candidates:
            sub_chatbot, selection_info, scores = candidates[0]
            logger.info(f"[DELEGATE] Selected sub: {sub_chatbot.name} (kw:{scores['keyword']:.3f}, emb:{scores['embedding']:.3f}, hybrid:{scores['hybrid']:.3f})")
            # 선택 근거 가시화 (디버깅/운영 확인용)
            yield "📊 **하위 후보 점수(상위 3)**\n"
            for i, (cb, _, sc) in enumerate(candidates[:3], 1):
                yield f"{i}. {cb.name} (id={cb.id}) → kw:{sc['keyword']}, emb:{sc['embedding']}, hybrid:{sc['hybrid']}\n"
            yield "\n"

            sub_chatbot, selection_info, scores = candidates[0]
            # DEBUG: logger.info(
            #     f"[DELEGATE] Single sub selected: {sub_chatbot.name} "
            #     f"(kw:{scores['keyword']}, emb:{scores['embedding']}, hybrid:{scores['hybrid']})"
            # )
            yield f"✅ **선택된 하위 챗봇: [{sub_chatbot.name}]** {selection_info}\n\n"
            yield from self._delegate_to_sub(sub_chatbot, message, session_id, context)
        else:
            yield from self._fallback_to_parent_or_self(message, session_id, context, confidence,
                                                         reason="적합한 하위 Agent를 찾을 수 없습니다")

    def _fallback_to_parent_or_self(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
        reason: str = "",
    ) -> Generator[str, None, None]:
        """하위 위임 실패 시 자체 응답으로 Fallback (상위 위임 제거)"""
        logger.info(f"[DELEGATE] Falling back to self: {reason}")
        yield f"❌ {reason}.\n"
        yield from self._execute_with_context(message, session_id, context)

    # ====================================================================
    # 상위 Agent 위임
    # ====================================================================

    def _delegate_to_parent(
        self,
        message: str,
        session_id: str,
        context: str,
        confidence: float,
    ) -> Generator[str, None, None]:
        """상위(부모) Agent로 위임"""
        if not self.chatbot_manager:
            logger.warning("[DELEGATE] No chatbot_manager, cannot delegate to parent")
            yield "❌ ChatbotManager가 설정되지 않아 부모 Agent로 위임할 수 없습니다.\n"
            yield from self._execute_with_context(message, session_id, context)
            return

        parent_id = self.chatbot_def.parent_id
        if not parent_id:
            logger.warning("[DELEGATE] No parent_id set")
            yield "⚠️ 부모 Agent가 없습니다. 현재 Agent로 답변합니다.\n"
            yield from self._execute_with_context(message, session_id, context)
            return

        parent_def = self.chatbot_manager.get_active(parent_id)
        if not parent_def:
            logger.warning(f"[DELEGATE] Parent '{parent_id}' not found")
            yield f"⚠️ 부모 Agent '{parent_id}'를 찾을 수 없습니다. 현재 Agent로 답변합니다.\n"
            yield from self._execute_with_context(message, session_id, context)
            return

        logger.info(
            f"[DELEGATION PATH] {self.chatbot_def.name} (L{self.chatbot_def.level}) "
            f"→ {parent_def.name} (L{parent_def.level}) | confidence={confidence}%"
        )
        yield f"\n📤 **[{self.chatbot_def.name}] → [{parent_def.name}]**로 위임합니다.\n"
        yield f"(Confidence: {confidence}% / Level: {self.chatbot_def.level} → {parent_def.level})\n\n"

        parent_executor = HierarchicalAgentExecutor(
            chatbot_def=parent_def,
            ingestion_client=self.ingestion,
            memory_manager=self.memory,
            chatbot_manager=self.chatbot_manager,
            accumulated_context=context,
            delegation_depth=self.delegation_depth + 1,
        )
        yield from parent_executor.execute(message, session_id)

    # ====================================================================
    # 공통 실행
    # ====================================================================

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

    # ====================================================================
    # 하위 Agent 선택 (하이브리드 방식)
    # ====================================================================

    def _select_sub_chatbot_hybrid_multi_for_delegation(self, message: str = None) -> bool:
        """
        위임 결정용: 하위 Agent 중 적합한 후보가 있는지 확인
        
        Args:
            message: 사용자 질문 (테스트에서는 None 가능)
        
        Returns:
            bool: 적합한 후보가 있으면 True
        """
        if not self.chatbot_manager or not self.chatbot_def.sub_chatbots:
            return False

        candidates = []
        for sub_ref in self.chatbot_def.sub_chatbots:
            sub_def = self.chatbot_manager.get_active(sub_ref.id)
            if sub_def:
                candidates.append(sub_def)

        if not candidates:
            return False

        # 실제 환경: message가 있으면 질문 적합성 검사
        if message:
            message_lower = message.lower()
            logger.info(f"[DELEGATION] Evaluating {len(candidates)} sub chatbots for message: {message[:50]}...")
            logger.info(f"[DELEGATION] Hybrid score threshold: {self.hybrid_score_threshold}")
            
            for sub_def in candidates:
                try:
                    # DEBUG: keywords 확인
                    # DEBUG: policy_keywords = []
                    # DEBUG: if getattr(sub_def, 'policy', None):
                    # DEBUG:     policy_keywords = sub_def.policy.get('keywords', []) or []
                    # DEBUG: direct_keywords = getattr(sub_def, 'keywords', [])
                    # DEBUG: logger.info(f"[DELEGATION DEBUG] {sub_def.id} keywords: policy={policy_keywords}, direct={direct_keywords}")
                    
                    kw_score = self._keyword_score(sub_def, message_lower)
                    emb_score = self._embedding_score(message, sub_def)
                    hybrid = self.KEYWORD_WEIGHT * kw_score + self.EMBEDDING_WEIGHT * emb_score
                    
                    # DEBUG: logger.info(f"[DELEGATION] Sub {sub_def.name}: kw={kw_score:.3f}, emb={emb_score:.3f}, hybrid={hybrid:.3f} (threshold={self.hybrid_score_threshold})")
                    
                    if hybrid >= self.hybrid_score_threshold:
                        logger.info(f"[DELEGATION] ✓ Found qualified sub: {sub_def.name} (hybrid={hybrid:.3f})")
                        return True
                except Exception as e:
                    logger.warning(f"[DELEGATION] Error evaluating sub {sub_def.id}: {e}")
                    continue
            logger.warning("[DELEGATION] ✗ No qualified sub found for this message")
            return False
        
        # 테스트 환경: message 없으면 하위 존재 여부만 확인
        return True

    def _select_sub_chatbot_hybrid(self, message: str) -> Tuple[Optional[ChatbotDef], str]:
        """하이브리드 하위 Agent 선택 (단일 반환)"""
        candidates = self._select_sub_chatbot_hybrid_multi(message)
        if candidates:
            best = candidates[0]
            info = f"(kw:{best[2]['keyword']}, emb:{best[2]['embedding']}, hybrid:{best[2]['hybrid']})"
            return best[0], info
        return None, ""

    def _select_sub_chatbot_hybrid_multi(
        self, message: str
    ) -> List[Tuple[ChatbotDef, str, dict]]:
        """하이브리드 하위 Agent 선택 (다중 반환)"""
        if not self.chatbot_manager:
            return []

        candidates = []
        for sub_ref in self.chatbot_def.sub_chatbots:
            sub_def = self.chatbot_manager.get_active(sub_ref.id)
            if not sub_def:
                continue
            candidates.append(sub_def)

        if not candidates:
            return []

        message_lower = message.lower()
        scores = []

        for sub_def in candidates:
            kw_score = self._keyword_score(sub_def, message_lower)
            emb_score = self._embedding_score(message, sub_def)
            hybrid = self.KEYWORD_WEIGHT * kw_score + self.EMBEDDING_WEIGHT * emb_score

            scores.append({
                'chatbot': sub_def,
                'keyword': round(kw_score, 3),
                'embedding': round(emb_score, 3),
                'hybrid': round(hybrid, 3),
            })

        scores.sort(key=lambda x: x['hybrid'], reverse=True)
        
        # DEBUG: logger.info(f"[DELEGATE DEBUG] scores list length: {len(scores)}")
        # DEBUG: if scores:
        # DEBUG:     logger.info(f"[DELEGATE DEBUG] first score: {scores[0]}")
        # DEBUG:     logger.info(f"[DELEGATE DEBUG] first score keys: {scores[0].keys() if isinstance(scores[0], dict) else 'N/A'}")
        # DEBUG: logger.info(f"[DELEGATE DEBUG] hybrid_threshold: {self.hybrid_score_threshold}, keyword_threshold: 0.3")

        # multi_sub_execution이면 전체 하위 챗봇 종합 우선
        # (사용자 요청: a/b/c/d 모두 조회 후 종합)
        if self.multi_sub_execution:
            selected = scores
        else:
            filtered = [s for s in scores if s['hybrid'] >= self.hybrid_score_threshold]
            # DEBUG: logger.info(f"[DELEGATE DEBUG] filtered length: {len(filtered)}, threshold: {self.hybrid_score_threshold}")

            # Fail-safe: if no candidates pass hybrid threshold, include best keyword match
            # if keyword_score >= 0.3 (at least 1 keyword matched)
            if not filtered:
                keyword_matches = [s for s in scores if s['keyword'] >= 0.3]
                # DEBUG: logger.info(f"[DELEGATE DEBUG] keyword_matches length: {len(keyword_matches)}")
                if keyword_matches:
                    keyword_matches.sort(key=lambda x: (x['keyword'], x['hybrid']), reverse=True)
                    filtered = keyword_matches[:1]
                elif scores:
                    filtered = scores[:1]

            selected = filtered[:self.max_parallel_subs]
            # DEBUG: logger.info(f"[DELEGATE DEBUG] selected length: {len(selected)}, max_parallel_subs: {self.max_parallel_subs}")
            # DEBUG: logger.info(f"[DELEGATE DEBUG] filtered type: {type(filtered)}, filtered: {filtered}")

        return [
            (s['chatbot'], f"(kw:{s['keyword']}, emb:{s['embedding']}, hybrid:{s['hybrid']})", {
                'keyword': s['keyword'],
                'embedding': s['embedding'],
                'hybrid': s['hybrid'],
            })
            for s in selected
        ]

    def _keyword_score(self, sub_def: ChatbotDef, message_lower: str) -> float:
        """키워드 매칭 점수 (0~1 정규화)

        우선순위:
        1) chatbot JSON policy.keywords
        2) chatbot.keywords 속성 (하위 호환)
        3) 코드 내 KEYWORDS_MAP (레거시 하위 호환)
        """
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

        # DEBUG: 위임 결정 관련 로그만 남김
        # DEBUG: logger.debug(f"[_keyword_score] {sub_def.id}: matched={matched}/{len(keywords)}, score={score:.3f}")

        return score

    def _embedding_score(self, message: str, sub_def: ChatbotDef) -> float:
        """임베딩 코사인 유사도 점수 (0~1)"""
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
        score = self._embedding_service.cosine_similarity(message, profile_text)
        # 안정성을 위해 반올림 (소수점 2자리)
        return round(score, 2)

    # ====================================================================
    # 다중 하위 Agent 실행
    # ====================================================================

    def _execute_multiple_subs(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, dict]],
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> List[Tuple[str, str, str]]:
        """다중 하위 Agent 실행"""
        if self.synthesis_mode == 'sequential':
            return self._execute_multiple_subs_sequential(
                sub_candidates, message, session_id, parent_context
            )
        return self._execute_multiple_subs_parallel(
            sub_candidates, message, session_id, parent_context
        )

    def _execute_multiple_subs_sequential(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, dict]],
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> List[Tuple[str, str, str]]:
        """순차적으로 다중 하위 Agent 실행"""
        # DEBUG: logger.debug(f"[DELEGATE] Sequential execution for {len(sub_candidates)} candidates")
        results = []
        for sub_chatbot, selection_info, scores in sub_candidates:
            try:
                response = self._execute_single_sub(sub_chatbot, message, session_id, parent_context)
                if response:
                    results.append((sub_chatbot.id, sub_chatbot.name, response))
            except Exception as e:
                logger.warning(f"[DELEGATE] {sub_chatbot.name} error: {e}")
                results.append((sub_chatbot.id, sub_chatbot.name, f"[오류: 응답 생성 실패 - {str(e)}]"))
        return results

    def _execute_multiple_subs_parallel(
        self,
        sub_candidates: List[Tuple[ChatbotDef, str, dict]],
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> List[Tuple[str, str, str]]:
        """병렬로 다중 하위 Agent 실행"""
        # DEBUG: logger.debug(f"[DELEGATE] Parallel execution for {len(sub_candidates)} candidates")
        results = []
        errors = []

        def execute_single(sub_chatbot: ChatbotDef) -> Tuple[str, str, Optional[str]]:
            try:
                response = self._execute_single_sub(sub_chatbot, message, session_id, parent_context)
                return (sub_chatbot.id, sub_chatbot.name, response)
            except Exception as e:
                logger.warning(f"[DELEGATE] {sub_chatbot.name} error: {e}")
                return (sub_chatbot.id, sub_chatbot.name, None)

        with ThreadPoolExecutor(max_workers=min(len(sub_candidates), 5)) as executor:
            future_to_sub = {executor.submit(execute_single, sub[0]): sub for sub in sub_candidates}
            for future in as_completed(future_to_sub):
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
        """단일 하위 Agent 실행 (전체 응답 수집) - HierarchicalAgentExecutor 사용"""
        logger.info(f"[DELEGATE] Executing sub: {sub_chatbot.name}(L{sub_chatbot.level}), DBs: {sub_chatbot.retrieval.db_ids}")
        
        try:
            # 하위 Executor도 HierarchicalAgentExecutor 사용 (2-tier 위임 지원)
            # accumulated_context는 비워두고, enhanced_message만으로 컨텍스트 전달
            sub_executor = HierarchicalAgentExecutor(
                sub_chatbot, 
                self.ingestion, 
                self.memory,
                self.chatbot_manager,
                accumulated_context="",  # 누적 컨텍스트 제거
                delegation_depth=self.delegation_depth + 1
            )
            enhanced_message = message
            # DEBUG: logger.info(f"[DELEGATE DEBUG] parent_context='{parent_context[:50]}...', message='{message[:50]}...'")
            if parent_context:
                enhanced_message = f"[상위 Agent 컨텍스트] {parent_context[:500]}...\n\n[질문] {message}"
            
            # DEBUG: logger.info(f"[DELEGATE] Enhanced message for {sub_chatbot.name}: {enhanced_message[:100]}...")
            # DEBUG: logger.info(f"[DELEGATE] Starting sub-executor for {sub_chatbot.name} with depth={self.delegation_depth + 1}")
            sub_answer = "".join(sub_executor.execute(enhanced_message, session_id))
            # DEBUG: logger.info(f"[DELEGATE] {sub_chatbot.name} completed, answer length: {len(sub_answer)}")
            
            source_header = f"🧾 {self._source_note(sub_chatbot)}\n\n"
            return source_header + sub_answer
        except Exception as e:
            logger.error(f"[DELEGATE] Error executing sub {sub_chatbot.name}: {e}", exc_info=True)
            return f"❌ 하위 Agent '{sub_chatbot.name}' 실행 중 오류 발생: {str(e)}"

    def _delegate_to_sub(
        self,
        sub_chatbot: ChatbotDef,
        message: str,
        session_id: str,
        parent_context: str = "",
    ) -> Generator[str, None, None]:
        """하위 Agent에게 위임 실행 (스트리밍) - HierarchicalAgentExecutor 사용"""
        # 하위 Executor도 HierarchicalAgentExecutor 사용 (2-tier 위임 지원)
        # accumulated_context는 비워두고, enhanced_message만으로 컨텍스트 전달
        sub_executor = HierarchicalAgentExecutor(
            sub_chatbot,
            self.ingestion,
            self.memory,
            self.chatbot_manager,
            accumulated_context="",  # 누적 컨텍스트 제거
            delegation_depth=self.delegation_depth + 1
        )
        enhanced_message = message
        if parent_context:
            enhanced_message = f"[상위 Agent 컨텍스트] {parent_context[:500]}...\n\n[질문] {message}"

        yield f"🧾 {self._source_note(sub_chatbot)}\n\n"
        
        # DEBUG: logger.info(f"[DELEGATE] Message in _delegate_to_sub: '{message[:50]}...'")
        
        yield from sub_executor.execute(enhanced_message, session_id)

    # ====================================================================
    # 응답 종합
    # ====================================================================

    def _synthesize_responses(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> str:
        """다중 하위 Agent 응답을 종합하여 하나의 응답 생성"""
        # DEBUG: logger.debug(f"[SYNTHESIZE] Starting with {len(sub_responses)} responses")
        
        if not sub_responses:
            # DEBUG: logger.warning("[SYNTHESIZE] No responses from sub-agents")
            return "❌ 하위 Agent로부터 응답을 받지 못했습니다."

        if len(sub_responses) == 1:
            _, name, response = sub_responses[0]
            # DEBUG: logger.debug(f"[SYNTHESIZE] Single response from {name}, returning directly")
            return f"**[{name}]**\n\n{response}"

        # DEBUG: logger.debug(f"[SYNTHESIZE] Building synthesis prompt for {len(sub_responses)} responses")
        synthesis_prompt = self._build_synthesis_prompt(parent_context, user_message, sub_responses)

        try:
            # DEBUG: logger.debug("[SYNTHESIZE] Calling LLM for synthesis")
            client = get_llm_client()
            messages = [
                {"role": "system", "content": synthesis_prompt["system"]},
                {"role": "user", "content": synthesis_prompt["user"]},
            ]
            response = client.chat.completions.create(
                model=self.chatbot_def.llm.model,
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
                stream=False,
            )
            synthesized = response.choices[0].message.content or ""
            synthesized += "\n\n---\n**참고 전문가:** " + ", ".join(
                [f"[{name}]" for _, name, _ in sub_responses]
            )
            # DEBUG: logger.debug(f"[SYNTHESIZE] LLM response length: {len(synthesized)}")
            return synthesized
        except Exception as e:
            # DEBUG: logger.warning(f"[SYNTHESIZE] LLM error: {e}, using fallback")
            return self._fallback_synthesis(sub_responses)

    def _build_synthesis_prompt(
        self,
        parent_context: str,
        user_message: str,
        sub_responses: List[Tuple[str, str, str]],
    ) -> dict:
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
