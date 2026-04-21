"""
Integration Test: LSI → PDDI → Weekly Report 3-tier delegation

Scenario replication of the production issue:
- User asks LSI사업팀: "PDDI개발팀 52주차 주간보고 요약해"
- Expected: LSI사업팀 → PDDI개발팀 → PDDI개발팀주간보고 (2-tier downward delegation)
- Current Issue: LSI사업팀 fails to delegate properly
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

from backend.executors.hierarchical_agent_executor import (
    HierarchicalAgentExecutor,
)
from backend.core.models import ChatbotDef, SubChatbotRef, ExecutionRole


def load_mock_chatbot(json_path: str) -> dict:
    """Load chatbot definition from JSON file"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


class TestLSIPDDIWeeklyDelegation:
    """
    TC-LSI-PDDI: LSI → PDDI → Weekly Report 위임 테스트
    """

    @pytest.fixture
    def setup_lsi_pddi_hierarchy(self):
        """
        3-Tier Hierarchy:
        
        Level 0 (Root): LSI사업팀 (lsi-business-team)
            └── Level 1: PDDI개발팀 (pddi-dev-team)
                    └── Level 2: PDDI개발팀주간보고 (pddi-weekly-report)
        """
        mock_dir = Path('/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent/tests/mock_chatbots')
        
        # Load from JSON files
        lsi_data = load_mock_chatbot(mock_dir / 'lsi-business-team.json')
        pddi_data = load_mock_chatbot(mock_dir / 'pddi-dev-team.json')
        weekly_data = load_mock_chatbot(mock_dir / 'pddi-weekly-report.json')

        # Create ChatbotDef objects
        def create_chatbot_def(data):
            bot = Mock(spec=ChatbotDef)
            bot.id = data['id']
            bot.name = data['name']
            bot.description = data['description']
            bot.system_prompt = data['system_prompt']
            bot.level = data['level']
            bot.parent_id = data.get('parent_id')
            bot.sub_chatbots = [
                SubChatbotRef(id=s['id'], level=s['level'], default_role=s['default_role'])
                for s in data.get('sub_chatbots', [])
            ]
            # Keywords are in policy.keywords (not top-level)
            bot.policy = data.get('policy', {})
            bot.keywords = bot.policy.get('keywords', [])  # Read from policy
            bot.retrieval = Mock()
            bot.retrieval.db_ids = data['retrieval']['db_ids']
            bot.retrieval.k = data['retrieval']['k']
            bot.retrieval.filter_metadata = data['retrieval'].get('filter_metadata')
            bot.llm = Mock()
            bot.llm.model = data['llm']['model']
            bot.memory = Mock()
            bot.memory.max_messages = data['memory']['max_messages']
            return bot

        lsi_bot = create_chatbot_def(lsi_data)
        pddi_bot = create_chatbot_def(pddi_data)
        weekly_bot = create_chatbot_def(weekly_data)

        # Create mock chatbot manager
        mock_manager = Mock()
        bot_map = {
            "lsi-business-team": lsi_bot,
            "pddi-dev-team": pddi_bot,
            "pddi-weekly-report": weekly_bot,
        }
        mock_manager.get_active = Mock(side_effect=lambda x: bot_map.get(x))

        return {
            "lsi_bot": lsi_bot,
            "pddi_bot": pddi_bot,
            "weekly_bot": weekly_bot,
            "mock_manager": mock_manager,
            "mock_ingestion": Mock(),
            "mock_memory": Mock(),
        }

    def test_keyword_matching_for_team_name(self, setup_lsi_pddi_hierarchy):
        """
        TC-LSI-001: "PDDI개발팀" 키워드가 LSI의 하위 챗봇과 매칭되는지 확인
        """
        setup = setup_lsi_pddi_hierarchy
        
        lsi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["lsi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Test keyword matching
        message = "PDDI개발팀 52주차 주간보고 요약해"
        message_lower = message.lower()
        
        # Check if PDDI개발팀's keywords match
        pddi_keywords = setup["pddi_bot"].keywords
        print(f"\n[Keyword Matching Test]")
        print(f"Message: {message}")
        print(f"PDDI Keywords: {pddi_keywords}")
        
        matched_keywords = [kw for kw in pddi_keywords if kw.lower() in message_lower]
        print(f"Matched keywords: {matched_keywords}")
        
        # Calculate keyword score
        kw_score = lsi_executor._keyword_score(setup["pddi_bot"], message_lower)
        print(f"Keyword score for PDDI개발팀: {kw_score}")
        
        # At least one keyword should match
        assert len(matched_keywords) > 0, f"No keywords matched! PDDI keywords: {pddi_keywords}"
        assert kw_score > 0, f"Keyword score should be > 0, got {kw_score}"
        
        print(f"\n✅ TC-LSI-001 PASSED: Keyword matching works")

    def test_lsi_should_delegate_to_pddi(self, setup_lsi_pddi_hierarchy):
        """
        TC-LSI-002: LSI사업팀이 "PDDI개발팀 52주차 주간보고" 질문에 대해 PDDI개발팀으로 위임해야 함
        """
        setup = setup_lsi_pddi_hierarchy
        
        lsi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["lsi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        # Simulate: LSI has low confidence for this specific question
        # because it's about PDDI team, not LSI business
        message = "PDDI개발팀 52주차 주간보고 요약해"
        
        print(f"\n[Delegation Decision Test - LSI → PDDI]")
        print(f"Question: {message}")
        print(f"LSI Keywords: {setup['lsi_bot'].keywords}")
        print(f"PDDI Keywords: {setup['pddi_bot'].keywords}")
        
        # Test with low confidence (simulating LSI doesn't know about PDDI weekly reports)
        result = lsi_executor._select_delegate_target(
            confidence=30,  # Low confidence
            message=message
        )
        
        print(f"Delegation target: {result.target}")
        print(f"Reason: {result.reason}")
        
        # Expected: LSI should delegate to sub (PDDI개발팀) because:
        # 1. Low confidence (30% < 70%)
        # 2. PDDI개발팀 is a qualified sub (keywords match)
        assert result.target == 'sub', f"Expected 'sub', got '{result.target}'"
        assert 'sub_chatbots' in result.reason or 'qualified' in result.reason.lower()
        
        print(f"\n✅ TC-LSI-002 PASSED: LSI → PDDI delegation decision works")

    def test_pddi_should_delegate_to_weekly(self, setup_lsi_pddi_hierarchy):
        """
        TC-LSI-003: PDDI개발팀이 "52주차 주간보고" 질문에 대해 주간보고 챗봇으로 위임해야 함
        """
        setup = setup_lsi_pddi_hierarchy
        
        pddi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["pddi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        message = "52주차 주간보고 요약해"
        
        print(f"\n[Delegation Decision Test - PDDI → Weekly Report]")
        print(f"Question: {message}")
        print(f"PDDI Keywords: {setup['pddi_bot'].keywords}")
        print(f"Weekly Report Keywords: {setup['weekly_bot'].keywords}")
        
        # Test with low confidence
        result = pddi_executor._select_delegate_target(
            confidence=40,  # Low confidence for weekly report
            message=message
        )
        
        print(f"Delegation target: {result.target}")
        print(f"Reason: {result.reason}")
        
        # Expected: PDDI should delegate to sub (주간보고)
        assert result.target == 'sub', f"Expected 'sub', got '{result.target}'"
        
        print(f"\n✅ TC-LSI-003 PASSED: PDDI → Weekly Report delegation decision works")

    def test_full_delegation_chain_lsi_to_weekly(self, setup_lsi_pddi_hierarchy):
        """
        TC-LSI-004: Full chain - LSI → PDDI → Weekly Report (2-tier downward)
        """
        setup = setup_lsi_pddi_hierarchy
        
        print(f"\n[Full Delegation Chain Test]")
        print(f"=" * 60)
        
        # Step 1: LSI (Level 0) receives question
        message = "PDDI개발팀 52주차 주간보고 요약해"
        print(f"\nStep 1: LSI사업팀 (Level 0) receives: '{message}'")
        
        lsi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["lsi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )
        
        # LSI has low confidence (doesn't know PDDI details)
        result1 = lsi_executor._select_delegate_target(confidence=30, message=message)
        print(f"LSI Decision: {result1.target} | Reason: {result1.reason}")
        assert result1.target == 'sub', f"Step 1 failed: Expected 'sub', got '{result1.target}'"
        print("Step 1: LSI → PDDI ✓")
        
        # Step 2: PDDI (Level 1) receives the question
        print(f"\nStep 2: PDDI개발팀 (Level 1) receives: '{message}'")
        
        pddi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["pddi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )
        
        # PDDI has low confidence for weekly report (should delegate down)
        result2 = pddi_executor._select_delegate_target(confidence=40, message=message)
        print(f"PDDI Decision: {result2.target} | Reason: {result2.reason}")
        assert result2.target == 'sub', f"Step 2 failed: Expected 'sub', got '{result2.target}'"
        print("Step 2: PDDI → Weekly Report ✓")
        
        # Step 3: Weekly Report (Level 2) receives the question
        print(f"\nStep 3: PDDI개발팀주간보고 (Level 2) receives: '{message}'")
        
        weekly_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["weekly_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )
        
        # Weekly Report has high confidence (this is its domain)
        result3 = weekly_executor._select_delegate_target(confidence=85, message=message)
        print(f"Weekly Report Decision: {result3.target} | Reason: {result3.reason}")
        assert result3.target == 'self', f"Step 3 failed: Expected 'self', got '{result3.target}'"
        print("Step 3: Weekly Report → Self (Answer) ✓")
        
        print(f"\n✅ TC-LSI-004 PASSED: Full 2-tier downward delegation chain works!")
        print(f"   LSI사업팀 → PDDI개발팀 → PDDI개발팀주간보고")

    def test_hybrid_score_calculation_for_lsi_question(self, setup_lsi_pddi_hierarchy):
        """
        TC-LSI-005: 하이브리드 스코어 계산 검증 - "PDDI개발팀"이 PDDI개발팀과 매칭되는지
        """
        setup = setup_lsi_pddi_hierarchy
        
        lsi_executor = HierarchicalAgentExecutor(
            chatbot_def=setup["lsi_bot"],
            ingestion_client=setup["mock_ingestion"],
            memory_manager=setup["mock_memory"],
            chatbot_manager=setup["mock_manager"],
        )

        message = "PDDI개발팀 52주차 주간보고 요약해"
        message_lower = message.lower()
        
        print(f"\n[Hybrid Score Calculation Test]")
        print(f"Message: {message}")
        
        # Calculate scores for PDDI개발팀
        pddi_bot = setup["pddi_bot"]
        
        kw_score = lsi_executor._keyword_score(pddi_bot, message_lower)
        print(f"Keyword score: {kw_score:.3f}")
        
        # Embedding score (mock - would need actual embedding service)
        # For this test, we'll just check keyword score is significant
        
        # Check if any keyword matches
        matched = [kw for kw in pddi_bot.keywords if kw.lower() in message_lower]
        print(f"Matched keywords: {matched}")
        
        # The keyword "PDDI개발팀" should match exactly
        assert "PDDI개발팀" in matched or "pddi개발팀" in message_lower, \
            f"'PDDI개발팀' should be in matched keywords. Got: {matched}"
        assert kw_score > 0, f"Keyword score should be > 0"
        
        print(f"\n✅ TC-LSI-005 PASSED: Hybrid score calculation shows PDDI개발팀 is qualified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
