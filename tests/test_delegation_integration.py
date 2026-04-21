"""
System/Integration tests for HierarchicalAgentExecutor delegation

End-to-end delegation scenarios:
- High confidence → direct answer
- Low confidence + sub_chatbots → sub delegation
- Low confidence + no sub + parent → parent delegation
- Max delegation depth exceeded
- Memory/context accumulation across delegations
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, PropertyMock

sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

from backend.executors.hierarchical_agent_executor import (
    HierarchicalAgentExecutor,
    DelegateResult,
)
from backend.core.models import ChatbotDef, SubChatbotRef, ExecutionRole


def make_chatbot_def(
    chatbot_id: str,
    name: str,
    level: int = 0,
    sub_chatbots: list = None,
    parent_id: str = None,
    system_prompt: str = "You are a helpful assistant.",
    description: str = "Test chatbot",
    db_ids: list = None,
    policy: dict = None,
):
    """Helper to create a mock ChatbotDef"""
    mock = Mock(spec=ChatbotDef)
    mock.id = chatbot_id
    mock.name = name
    mock.level = level
    mock.sub_chatbots = sub_chatbots or []
    mock.parent_id = parent_id
    mock.system_prompt = system_prompt
    mock.description = description
    mock.is_root = (parent_id is None)
    mock.policy = policy or {}
    
    # Retrieval settings
    mock.retrieval = Mock()
    mock.retrieval.db_ids = db_ids or ["default-db"]
    
    # Memory settings
    mock.memory = Mock()
    mock.memory.max_messages = 20
    
    # LLM settings
    mock.llm = Mock()
    mock.llm.model = "test-model"
    
    return mock


class TestDirectAnswerScenario:
    """Scenario: High confidence → direct answer"""
    
    @pytest.fixture
    def setup_direct_answer(self):
        """Setup executor that will answer directly"""
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-hr-benefit",
            name="HR Benefit Bot",
            level=2,
            parent_id="chatbot-hr",
            db_ids=["hr-benefit-db"],
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
        )
        executor.delegation_threshold = 70
        
        return executor
    
    def test_high_confidence_no_delegation(self, setup_direct_answer):
        """TC-SYS-001: High confidence should produce direct answer without delegation"""
        executor = setup_direct_answer
        
        result = executor._select_delegate_target(confidence=85, message="테스트 질문")
        
        assert result.target == 'self'
        assert 'self' == result.target


class TestSubDelegationScenario:
    """Scenario: Low confidence + sub_chatbots → sub delegation"""
    
    @pytest.fixture
    def setup_sub_delegation(self):
        """Setup child executor with sub_chatbots (level=2, not parent)"""
        sub_refs = [
            SubChatbotRef(id='chatbot-hr-policy', level=3, default_role=ExecutionRole.AGENT),
            SubChatbotRef(id='chatbot-hr-benefit', level=3, default_role=ExecutionRole.AGENT),
        ]
        
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-hr",
            name="HR Bot",
            level=2,  # Child level (>=2), can delegate to sub
            sub_chatbots=sub_refs,
            parent_id="chatbot-company",
            db_ids=["hr-db"],
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        mock_manager = Mock()  # chatbot_manager 추가
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
            chatbot_manager=mock_manager,  # 하위 확인용
        )
        executor.delegation_threshold = 70
        
        return executor
    
    def test_child_low_confidence_delegates_to_sub(self, setup_sub_delegation):
        """TC-SYS-002: Child (level=2+) with low confidence should delegate to sub"""
        executor = setup_sub_delegation
        executor.chatbot_manager = Mock()  # 하위 확인용
        
        result = executor._select_delegate_target(confidence=40, message="테스트 질문")
        
        assert result.target == 'sub'
        assert 'has qualified sub_chatbots' in result.reason
    
    def test_child_sub_delegation_priority_over_parent(self, setup_sub_delegation):
        """TC-SYS-003: Child with sub_chatbots should prefer sub over parent"""
        executor = setup_sub_delegation
        executor.chatbot_manager = Mock()  # 하위 확인용
        
        result = executor._select_delegate_target(confidence=30, message="테스트 질문")
        
        assert result.target == 'sub'
        assert 'has qualified sub_chatbots' in result.reason


class TestParentDelegationScenario:
    """Scenario: Low confidence + no sub + parent → parent delegation"""
    
    @pytest.fixture
    def setup_parent_delegation(self):
        """Setup leaf executor with parent but no sub_chatbots"""
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-hr-benefit",
            name="HR Benefit Bot",
            level=2,
            sub_chatbots=[],
            parent_id="chatbot-hr",
            db_ids=["hr-benefit-db"],
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
        )
        executor.delegation_threshold = 70
        executor.enable_parent_delegation = True
        
        return executor
    
    def test_leaf_low_confidence_delegates_to_parent(self, setup_parent_delegation):
        """TC-SYS-004: Leaf with low confidence should delegate to parent"""
        executor = setup_parent_delegation
        
        result = executor._select_delegate_target(confidence=30, message="테스트 질문")
        
        assert result.target == 'parent'
    
    def test_parent_delegation_disabled(self, setup_parent_delegation):
        """TC-SYS-005: With parent delegation disabled, should fallback"""
        executor = setup_parent_delegation
        executor.enable_parent_delegation = False
        
        result = executor._select_delegate_target(confidence=30, message="테스트 질문")
        
        assert result.target == 'fallback'


class TestMaxDelegationDepthScenario:
    """Scenario: Max delegation depth exceeded"""
    
    @pytest.fixture
    def setup_deep_delegation(self):
        """Setup executor at maximum delegation depth"""
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-deep",
            name="Deep Bot",
            level=3,
            sub_chatbots=[
                SubChatbotRef(id='deeper-bot', level=4, default_role=ExecutionRole.AGENT),
            ],
            parent_id="chatbot-mid",
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
            delegation_depth=5,  # MAX_DELEGATION_DEPTH
        )
        
        return executor
    
    def test_max_depth_produces_warning(self, setup_deep_delegation):
        """TC-SYS-006: Max depth should yield warning message"""
        executor = setup_deep_delegation
        
        with patch.object(executor, '_execute_with_context', return_value=iter(["fallback answer"])):
            with patch.object(executor, '_retrieve', return_value=""):
                result = list(executor.execute("test message", "session-1"))
        
        full_text = "".join(result)
        assert "최대 위임 깊이" in full_text or "⚠️" in full_text


class TestFallbackScenario:
    """Scenario: No delegation options available"""
    
    @pytest.fixture
    def setup_isolated_bot(self):
        """Setup executor with no sub_chatbots and no parent"""
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-isolated",
            name="Isolated Bot",
            level=0,
            sub_chatbots=[],
            parent_id=None,
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
        )
        executor.delegation_threshold = 70
        
        return executor
    
    def test_isolated_bot_falls_back(self, setup_isolated_bot):
        """TC-SYS-007: Bot without sub or parent should fallback"""
        executor = setup_isolated_bot
        
        result = executor._select_delegate_target(confidence=30, message="테스트 질문")
        
        assert result.target == 'fallback'


class TestContextAccumulation:
    """Scenario: Context accumulates across delegations"""
    
    @pytest.fixture
    def setup_with_accumulated_context(self):
        """Setup executor with pre-accumulated context"""
        chatbot = make_chatbot_def(
            chatbot_id="chatbot-parent",
            name="Parent Bot",
            level=0,
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        accumulated = "Sub agent found: 급여 관련 기본 정보"
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
            accumulated_context=accumulated,
            delegation_depth=1,
        )
        
        return executor, accumulated
    
    def test_context_carries_from_sub(self, setup_with_accumulated_context):
        """TC-SYS-008: Accumulated context from sub should be preserved"""
        executor, accumulated = setup_with_accumulated_context
        
        current_context = "Parent search results about 급여"
        combined = executor._combine_contexts(accumulated, current_context)
        
        assert accumulated in combined
        assert current_context in combined
        assert "[상위 컨텍스트]" in combined
        assert "[현재 검색 결과]" in combined
    
    def test_delegation_depth_increments(self, setup_with_accumulated_context):
        """TC-SYS-009: Delegation depth should be set correctly"""
        executor, _ = setup_with_accumulated_context
        
        assert executor.delegation_depth == 1


class TestDelegationThresholdVariations:
    """Scenario: Different threshold configurations"""
    
    def test_custom_threshold_from_policy(self):
        """TC-SYS-010: Custom threshold from chatbot policy"""
        chatbot = make_chatbot_def(
            chatbot_id="custom-bot",
            name="Custom Bot",
            policy={'delegation_threshold': 50},
        )
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=Mock(),
            memory_manager=Mock(),
        )
        
        assert executor.delegation_threshold == 50
    
    def test_default_threshold_when_no_policy(self):
        """TC-SYS-011: Default threshold when policy is empty"""
        chatbot = make_chatbot_def(
            chatbot_id="default-bot",
            name="Default Bot",
            policy={},
        )
        
        executor = HierarchicalAgentExecutor(
            chatbot_def=chatbot,
            ingestion_client=Mock(),
            memory_manager=Mock(),
        )
        
        assert executor.delegation_threshold == 70  # DEFAULT_DELEGATION_THRESHOLD


class TestCriticalDelegationScenarios:
    """Critical scenarios: Parent answering self-domain vs delegating to sub"""
    
    @pytest.fixture
    def setup_parent_with_sub(self):
        """Setup Parent A with sub chatbot D"""
        # D 설정 (전문분야: tech-devops)
        sub_d = make_chatbot_def(
            chatbot_id="chatbot-tech-devops",
            name="DevOps Bot D",
            level=2,
            db_ids=["devops-db"],
            system_prompt="당신은 DevOps 전문가입니다. docker, kubernetes에 대해 답변하세요.",
        )
        
        # A 설정 (전문분야: HR)
        sub_refs = [
            SubChatbotRef(id='chatbot-tech-devops', level=2, default_role=ExecutionRole.AGENT),
        ]
        
        parent_a = make_chatbot_def(
            chatbot_id="chatbot-hr",
            name="HR Bot A",
            level=1,
            sub_chatbots=sub_refs,
            parent_id="company-root",
            db_ids=["hr-db"],
            system_prompt="당신은 HR 전문가입니다. 인사/복지에 대해 답변하세요.",
        )
        
        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        mock_manager = Mock()
        mock_manager.get_active = Mock(return_value=sub_d)
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=parent_a,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
            chatbot_manager=mock_manager,
        )
        executor_a.delegation_threshold = 70
        
        return executor_a, sub_d
    
    def test_parent_answers_self_domain_question(self, setup_parent_with_sub):
        """
        TC-CRIT-001: Parent A에게 A의 전문분야(HR) 질문 → A가 직접 답변
        
        시나리오: "연차 정책 알려줘" (HR 관련 - A의 전문분야)
        기대: A가 직접 답변, 하위 D로 위임하지 않음
        """
        executor_a, sub_d = setup_parent_with_sub
        
        # A가 HR 관련 질문에 높은 confidence를 갖도록 설정
        executor_a._retrieve = Mock(return_value="연차 정책: 1년차 15일, 매 2년마다 1일 추가...")
        executor_a._calculate_confidence = Mock(return_value=85)  # 높은 confidence
        executor_a._stream_chat = Mock(return_value=iter(["연차는 1년차에 15일입니다."]))
        
        # 위임 메서드 추적
        executor_a._delegate_to_sub_chatbots = Mock(return_value=iter([]))
        executor_a._delegate_to_parent = Mock(return_value=iter([]))
        
        # 실행
        result = list(executor_a.execute("연차 정책 알려줘", "sess-1"))
        result_text = "".join(result)
        
        # 검증
        assert executor_a._delegate_to_sub_chatbots.call_count == 0, \
            "A의 전문분야 질문에 하위로 위임하면 안 됨"
        assert executor_a._delegate_to_parent.call_count == 0, \
            "A의 전문분야 질문에 상위로 위임하면 안 됨"
        assert "연차" in result_text or "15일" in result_text, \
            "A가 직접 답변해야 함"
    
    def test_parent_delegates_to_sub_for_sub_domain_question(self, setup_parent_with_sub):
        """
        TC-CRIT-002: Parent A에게 D의 전문분야(DevOps) 질문 → D가 실제로 답변
        
        시나리오: "docker 사용법 알려줘" (DevOps 관련 - D의 전문분야)
        기대: A가 하위로 위임 → D가 답변 (A가 "D에게 질문하세요" 하면 안 됨)
        """
        executor_a, sub_d = setup_parent_with_sub
        
        # A는 HR 전문가라 DevOps 질문에 낮은 confidence
        executor_a._retrieve = Mock(return_value="")  # 검색 결과 없음
        executor_a._calculate_confidence = Mock(return_value=15)  # 낮은 confidence
        
        # D는 DevOps 전문가라 높은 confidence
        sub_d._retrieve = Mock(return_value="docker는 컨테이너 기술입니다...")
        sub_d._calculate_confidence = Mock(return_value=90)
        
        # 위임 실행 모의
        def mock_delegate_to_sub(*args, **kwargs):
            # D가 답변하는 것을 시뮬레이션
            yield "📋 이 질문은 전문가 상담이 필요합니다.\n\n"
            yield "(HR Bot A 신뢰도: 15% → 하위 Agent 위임)\n\n"
            yield "---\n📡 **전문가 챗봇을 호출합니다...**\n\n"
            yield "📊 **하위 후보 점수(상위 3)**\n"
            yield "1. DevOps Bot D (id=chatbot-tech-devops)\n\n"
            yield "✅ **선택된 하위 챗봇: [DevOps Bot D]**\n\n"
            yield "📢 **[DevOps Bot D]** (신뢰도: 90% / Level: 2)\n"
            yield "🧾 출처: DevOps Bot D (id=chatbot-tech-devops, level=2, db=devops-db)\n\n"
            yield "Docker는 컨테이너 가상화 기술입니다."
        
        executor_a._delegate_to_sub_chatbots = mock_delegate_to_sub
        executor_a._delegate_to_parent = Mock(return_value=iter([]))
        
        # 실행
        result = list(executor_a.execute("docker 사용법 알려줘", "sess-2"))
        result_text = "".join(result)
        
        # 검증
        assert executor_a._delegate_to_parent.call_count == 0, \
            "하위가 있으면 상위로 위임하면 안 됨"
        assert "DevOps Bot D" in result_text, \
            "D가 답변해야 함"
        assert "Docker는 컨테이너" in result_text, \
            "D가 실제 내용을 답변해야 함"
        assert "D에게 질문하세요" not in result_text.lower(), \
            "A가 fallback해서 'D에게 질문하세요' 하면 안 됨"
    
    def test_sub_actually_answers_not_fallback(self, setup_parent_with_sub):
        """
        TC-CRIT-003: D가 위임받은 질문에 실제로 답변 (fallback 하지 않음)
        
        시나리오: D가 docker 질문을 받았을 때 실제로 답변
        """
        executor_a, sub_d = setup_parent_with_sub
        
        # D executor 생성
        mock_memory_d = Mock()
        mock_memory_d.get_history.return_value = []
        executor_d = HierarchicalAgentExecutor(
            chatbot_def=sub_d,
            ingestion_client=Mock(),
            memory_manager=mock_memory_d,
        )
        executor_d.delegation_threshold = 70
        
        # D는 docker 질문에 높은 confidence
        executor_d._retrieve = Mock(return_value="docker run 명령어는...")
        executor_d._calculate_confidence = Mock(return_value=92)
        executor_d._stream_chat = Mock(return_value=iter(["docker run -d -p 80:80 nginx"]))
        
        # D가 직접 답변 (fallback 아님)
        result = list(executor_d.execute("docker nginx �우는 법", "sess-3"))
        result_text = "".join(result)
        
        # 검증
        assert "docker run" in result_text, \
            "D가 실제 답변을 제공해야 함"
        assert "fallback" not in result_text.lower(), \
            "fallback 메시지가 나오면 안 됨"
        assert "모릅니다" not in result_text.lower(), \
            "모른다고 하면 안 됨"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
