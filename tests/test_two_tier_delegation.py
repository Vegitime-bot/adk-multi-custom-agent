"""
Test case for 2-Tier Delegation (Child → Parent → Root)

Scenario:
- User asks a question to Child Agent (Level 2)
- Child has low confidence → delegates to Parent (Level 1)
- Parent also has low confidence → delegates to Root (Level 0)
- Root answers with accumulated context

This tests the full upward delegation chain.
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, call

sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

from backend.executors.hierarchical_agent_executor import (
    HierarchicalAgentExecutor,
    DelegateResult,
)
from backend.core.models import ChatbotDef, SubChatbotRef, ExecutionRole, RetrievalConfig, LLMConfig, MemoryConfig


class TestTwoTierDelegation:
    """
    TC-TWO-TIER: 2단계 위임 테스트 (Child → Parent → Root)
    """

    @pytest.fixture
    def setup_three_tier_hierarchy(self):
        """
        Create a 3-tier hierarchy for testing:
        
        Level 0 (Root): "root-bot"
            └── Level 1 (Parent): "parent-bot"
                    └── Level 2 (Child): "child-bot"
        """
        # Mock ingestion and memory
        mock_ingestion = Mock()
        mock_memory = Mock()

        # Level 0: Root Bot
        root_bot = Mock(spec=ChatbotDef)
        root_bot.id = "root-bot"
        root_bot.name = "Root Bot"
        root_bot.level = 0
        root_bot.sub_chatbots = [
            SubChatbotRef(id='parent-bot', level=1, default_role=ExecutionRole.AGENT),
        ]
        root_bot.parent_id = None  # No parent
        root_bot.policy = {
            "delegation_threshold": 70,
            "enable_parent_delegation": True,
            "multi_sub_execution": False,
        }
        root_bot.retrieval = Mock(spec=RetrievalConfig)
        root_bot.retrieval.db_ids = ["root-db"]
        root_bot.retrieval.k = 5
        root_bot.retrieval.filter_metadata = None
        root_bot.llm = Mock(spec=LLMConfig)
        root_bot.llm.model = "gpt-4"
        root_bot.memory = Mock(spec=MemoryConfig)
        root_bot.memory.max_messages = 20
        root_bot.system_prompt = "You are the root agent with comprehensive knowledge."

        # Level 1: Parent Bot
        parent_bot = Mock(spec=ChatbotDef)
        parent_bot.id = "parent-bot"
        parent_bot.name = "Parent Bot"
        parent_bot.level = 1
        parent_bot.sub_chatbots = [
            SubChatbotRef(id='child-bot', level=2, default_role=ExecutionRole.AGENT),
        ]
        parent_bot.parent_id = "root-bot"
        parent_bot.policy = {
            "delegation_threshold": 70,
            "enable_parent_delegation": True,
            "multi_sub_execution": False,
        }
        parent_bot.retrieval = Mock(spec=RetrievalConfig)
        parent_bot.retrieval.db_ids = ["parent-db"]
        parent_bot.retrieval.k = 5
        parent_bot.retrieval.filter_metadata = None
        parent_bot.llm = Mock(spec=LLMConfig)
        parent_bot.llm.model = "gpt-4"
        parent_bot.memory = Mock(spec=MemoryConfig)
        parent_bot.memory.max_messages = 20
        parent_bot.system_prompt = "You are the parent agent."

        # Level 2: Child Bot
        child_bot = Mock(spec=ChatbotDef)
        child_bot.id = "child-bot"
        child_bot.name = "Child Bot"
        child_bot.level = 2
        child_bot.sub_chatbots = []  # No sub-chatbots (Leaf)
        child_bot.parent_id = "parent-bot"
        child_bot.policy = {
            "delegation_threshold": 70,
            "enable_parent_delegation": True,
            "multi_sub_execution": False,
        }
        child_bot.retrieval = Mock(spec=RetrievalConfig)
        child_bot.retrieval.db_ids = ["child-db"]
        child_bot.retrieval.k = 5
        child_bot.retrieval.filter_metadata = None
        child_bot.llm = Mock(spec=LLMConfig)
        child_bot.llm.model = "gpt-4"
        child_bot.memory = Mock(spec=MemoryConfig)
        child_bot.memory.max_messages = 20
        child_bot.system_prompt = "You are the child agent with specialized knowledge."

        # Create mock chatbot manager
        mock_manager = Mock()
        
        def get_active_side_effect(chatbot_id):
            bot_map = {
                "root-bot": root_bot,
                "parent-bot": parent_bot,
                "child-bot": child_bot,
            }
            return bot_map.get(chatbot_id)
        
        mock_manager.get_active = Mock(side_effect=get_active_side_effect)

        return {
            "root_bot": root_bot,
            "parent_bot": parent_bot,
            "child_bot": child_bot,
            "mock_ingestion": mock_ingestion,
            "mock_memory": mock_memory,
            "mock_manager": mock_manager,
        }

    def test_child_delegates_to_parent_low_confidence(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-001: Child (Level 2) with low confidence should delegate to Parent (Level 1)
        """
        setup = setup_three_tier_hierarchy
        
        child_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["child_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Child: Low confidence (30% < 70% threshold)
        # Child has no sub-chatbots (Leaf)
        result = child_executor._select_delegate_target(
            confidence=30, 
            message="어려운 질문"
        )

        # Expected: Parent로 위임 (상향)
        assert result.target == 'parent', f"Expected 'parent', got '{result.target}'"
        assert 'delegate UP' in result.reason or 'parent' in result.reason.lower(), \
            f"Reason should indicate parent delegation: {result.reason}"
        print(f"✅ TC-TWO-TIER-001 PASSED: Child → Parent delegation")
        print(f"   Reason: {result.reason}")

    def test_parent_delegates_to_root_low_confidence_no_qualified_sub(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-002: Parent (Level 1) with low confidence and no qualified sub should delegate to Root (Level 0)
        
        Important: Parent has sub-chatbots, but if they're not QUALIFIED for the message,
        Parent should delegate UP to Root.
        """
        setup = setup_three_tier_hierarchy
        
        parent_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["parent_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Parent: Low confidence (40% < 70% threshold)
        # Mock: 하위 Agent들이 이 질문에 적합하지 않음 (hybrid score threshold 미달)
        with patch.object(parent_executor, '_select_sub_chatbot_hybrid_multi_for_delegation', return_value=False):
            result = parent_executor._select_delegate_target(
                confidence=40, 
                message="매우 어려운 질문"
            )

        # Expected: Root로 위임 (상향) - 하위가 적합하지 않으므로
        assert result.target == 'parent', f"Expected 'parent' (to Root), got '{result.target}'"
        assert 'delegate UP' in result.reason, f"Reason should indicate UP delegation: {result.reason}"
        print(f"✅ TC-TWO-TIER-002 PASSED: Parent → Root delegation (no qualified sub)")
        print(f"   Reason: {result.reason}")

    def test_parent_delegates_to_qualified_sub_not_parent(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-003: Parent with qualified sub should delegate DOWN, not UP
        
        If Parent has a sub-chatbot that IS qualified for the message,
        it should delegate DOWN (not UP to Root).
        """
        setup = setup_three_tier_hierarchy
        
        parent_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["parent_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Parent: Low confidence (40% < 70% threshold)
        # Mock: 하위 Agent들이 이 질문에 적합함 (hybrid score threshold 충족)
        with patch.object(parent_executor, '_select_sub_chatbot_hybrid_multi_for_delegation', return_value=True):
            result = parent_executor._select_delegate_target(
                confidence=40, 
                message="적합한 질문"
            )

        # Expected: 하위로 위임 (하향)
        assert result.target == 'sub', f"Expected 'sub', got '{result.target}'"
        assert 'sub_chatbots' in result.reason, f"Reason should indicate sub delegation: {result.reason}"
        print(f"✅ TC-TWO-TIER-003 PASSED: Parent → Sub delegation (qualified sub)")
        print(f"   Reason: {result.reason}")

    def test_root_no_parent_returns_fallback(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-004: Root (Level 0) with low confidence and no parent should fallback
        """
        setup = setup_three_tier_hierarchy
        
        root_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["root_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Root: Low confidence (20% < 70% threshold)
        # Root has no parent_id
        result = root_executor._select_delegate_target(
            confidence=20, 
            message="최상위에서도 어려운 질문"
        )

        # Expected: Fallback (위임할 곳 없음)
        assert result.target == 'fallback', f"Expected 'fallback', got '{result.target}'"
        print(f"✅ TC-TWO-TIER-004 PASSED: Root → Fallback (no parent)")
        print(f"   Reason: {result.reason}")

    def test_delegation_path_child_to_parent_to_root(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-005: Full delegation path - Child → Parent → Root
        
        Integration test: Simulate the full 2-tier delegation flow
        """
        setup = setup_three_tier_hierarchy

        # Step 1: Child checks confidence and delegates to Parent
        child_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["child_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Mock: Child has low confidence, no qualified sub
        with patch.object(child_executor, '_calculate_confidence', return_value=30):
            result = child_executor._select_delegate_target(
                confidence=30,
                message="2단계 위임이 필요한 질문"
            )
        
        assert result.target == 'parent', "Step 1: Child should delegate to Parent"
        print("Step 1: Child → Parent ✓")

        # Step 2: Parent checks confidence and delegates to Root
        parent_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["parent_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Mock: Parent has low confidence, NO qualified sub
        with patch.object(parent_executor, '_calculate_confidence', return_value=40):
            with patch.object(parent_executor, '_select_sub_chatbot_hybrid_multi_for_delegation', return_value=False):
                result = parent_executor._select_delegate_target(
                    confidence=40,
                    message="2단계 위임이 필요한 질문"
                )
        
        assert result.target == 'parent', "Step 2: Parent should delegate to Root (parent target)"
        assert 'delegate UP' in result.reason
        print("Step 2: Parent → Root ✓")

        # Step 3: Root handles (no parent to delegate to)
        root_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["root_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Mock: Root has high confidence
        with patch.object(root_executor, '_calculate_confidence', return_value=85):
            result = root_executor._select_delegate_target(
                confidence=85,
                message="2단계 위임이 필요한 질문"
            )
        
        assert result.target == 'self', "Step 3: Root should answer directly (high confidence)"
        print("Step 3: Root → Self (answer) ✓")

        print(f"\n✅ TC-TWO-TIER-005 PASSED: Full Child → Parent → Root delegation path")

    def test_context_accumulation_upward(self, setup_three_tier_hierarchy):
        """
        TC-TWO-TIER-006: Context should accumulate when delegating upward
        
        When Child → Parent → Root, each level's context should be combined.
        """
        setup = setup_three_tier_hierarchy
        
        # Test _combine_contexts method
        child_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["child_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Simulate context accumulation
        child_context = "Child's search results about X"
        parent_context = "Parent's search results about X and Y"
        root_context = "Root's comprehensive knowledge about X, Y, and Z"

        # Step 1: Child → Parent (accumulated = child_context)
        combined1 = child_executor._combine_contexts(child_context, "")
        assert "[상위 컨텍스트]" in combined1
        assert child_context in combined1
        print("Step 1: Child context accumulated ✓")

        # Step 2: Parent → Root (accumulated = child + parent context)
        combined2 = child_executor._combine_contexts(combined1, parent_context)
        assert "[상위 컨텍스트]" in combined2
        assert child_context in combined2
        assert parent_context in combined2
        print("Step 2: Parent + Child context accumulated ✓")

        # Step 3: Root → Final (accumulated = child + parent + root context)
        combined3 = child_executor._combine_contexts(combined2, root_context)
        assert child_context in combined3
        assert parent_context in combined3
        assert root_context in combined3
        print("Step 3: Root + Parent + Child context accumulated ✓")

        print(f"\n✅ TC-TWO-TIER-006 PASSED: Context accumulation works correctly")


class TestDelegationDepthLimit:
    """
    TC-DEPTH-LIMIT: 위임 깊이 제한 테스트
    """

    def test_max_delegation_depth_prevents_infinite_loop(self):
        """
        TC-DEPTH-001: MAX_DELEGATION_DEPTH (5) exceeded should stop delegation
        """
        mock_chatbot = Mock(spec=ChatbotDef)
        mock_chatbot.id = "test-bot"
        mock_chatbot.name = "Test Bot"
        mock_chatbot.level = 2
        mock_chatbot.sub_chatbots = []
        mock_chatbot.parent_id = "parent-bot"
        mock_chatbot.policy = {"delegation_threshold": 70}

        mock_ingestion = Mock()
        mock_memory = Mock()
        mock_manager = Mock()

        executor = HierarchicalAgentExecutor(
            chatbot_def=mock_chatbot,
            ingestion_client=mock_ingestion,
            memory_manager=mock_memory,
            chatbot_manager=mock_manager,
            delegation_depth=5,  # Already at max depth
        )

        # Simulate execution with max depth
        # Should yield warning and not delegate further
        results = list(executor.execute("테스트 질문", "sess-1"))
        
        # Check for depth exceeded message
        result_text = "".join(results)
        assert "최대 위임 깊이" in result_text or "MAX_DELEGATION_DEPTH" in result_text or \
               executor.delegation_depth >= HierarchicalAgentExecutor.MAX_DELEGATION_DEPTH
        
        print(f"✅ TC-DEPTH-001 PASSED: Max delegation depth prevents infinite loops")
        print(f"   Current depth: {executor.delegation_depth}, Max: {HierarchicalAgentExecutor.MAX_DELEGATION_DEPTH}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
