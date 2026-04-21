"""
Test 3-tier delegation: L0 -> L1 -> L2

Scenarios:
1. Level 0 (LSI사업팀) 질문 -> Level 1 (PDDI개발팀) -> Level 2 (주간보고) 위임
2. Level 1 (PDDI개발팀) 질문 -> Level 2 (주간보고) 위임
3. Level 2 직접 질문
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')
sys.path.insert(0, str(Path(__file__).parent))

from mock_db import mock_retrieve, mock_generate_answer
from backend.executors.hierarchical_agent_executor import (
    HierarchicalAgentExecutor,
    DelegateResult,
)
from backend.core.models import ChatbotDef, ExecutionRole


class MockChatbotManager:
    """Mock ChatbotManager for testing"""
    
    def __init__(self, chatbots_dir):
        self.chatbots = {}
        self._load_chatbots(chatbots_dir)
    
    def _load_chatbots(self, chatbots_dir):
        import json
        chatbots_dir = Path(chatbots_dir)
        for json_file in chatbots_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
                self.chatbots[data["id"]] = self._create_chatbot_def(data)
    
    def _create_chatbot_def(self, data):
        """Create ChatbotDef from JSON data"""
        chatbot = Mock(spec=ChatbotDef)
        chatbot.id = data["id"]
        chatbot.name = data["name"]
        chatbot.description = data.get("description", "")
        chatbot.level = data.get("level", 0)
        chatbot.parent_id = data.get("parent_id")
        chatbot.role = ExecutionRole.AGENT if data.get("role") == "agent" else ExecutionRole.TOOL
        chatbot.keywords = data.get("keywords", [])
        chatbot.policy = data.get("policy", {})
        
        # Mock sub_chatbots as list of objects with id and level
        sub_chatbots = []
        for sub in data.get("sub_chatbots", []):
            sub_ref = Mock()
            sub_ref.id = sub["id"]
            sub_ref.level = sub["level"]
            sub_chatbots.append(sub_ref)
        chatbot.sub_chatbots = sub_chatbots
        
        # Mock retrieval
        retrieval = Mock()
        retrieval.db_ids = data.get("retrieval", {}).get("db_ids", [])
        retrieval.k = 3  # Default k value
        retrieval.filter_metadata = None
        chatbot.retrieval = retrieval
        
        # Mock llm
        llm = Mock()
        llm.model = data.get("llm", {}).get("model", "gpt-4o-mini")
        chatbot.llm = llm
        
        chatbot.system_prompt = data.get("system_prompt", "")
        
        return chatbot
    
    def get_active(self, chatbot_id):
        return self.chatbots.get(chatbot_id)
    
    def list_active(self):
        return list(self.chatbots.values())


class TestThreeTierDelegation:
    """Test 3-tier delegation flow"""
    
    @pytest.fixture
    def chatbot_manager(self):
        chatbots_dir = Path(__file__).parent / "mock_chatbots"
        return MockChatbotManager(chatbots_dir)
    
    @pytest.fixture
    def mock_ingestion(self):
        """Mock ingestion client"""
        ingestion = Mock()
        
        def mock_search(db_ids, query, k=3, filter_metadata=None):
            return mock_retrieve(db_ids, query, k)
        
        ingestion.search = mock_search
        return ingestion
    
    @pytest.fixture
    def mock_memory(self):
        class MockMemoryManager:
            def __init__(self):
                self.sessions = {}
            
            def get_history(self, chatbot_id, session_id):
                key = f"{chatbot_id}:{session_id}"
                return self.sessions.get(key, [])
            
            def add_message(self, chatbot_id, session_id, role, content):
                key = f"{chatbot_id}:{session_id}"
                if key not in self.sessions:
                    self.sessions[key] = []
                self.sessions[key].append({"role": role, "content": content})
        
        return MockMemoryManager()
    
    def test_l0_to_l1_to_l2_delegation(self, chatbot_manager, mock_ingestion, mock_memory):
        """Test: Level 0 -> Level 1 -> Level 2 delegation chain"""
        l0_chatbot = chatbot_manager.get_active("lsi-business-team")
        assert l0_chatbot is not None
        
        # Create L0 executor
        executor = HierarchicalAgentExecutor(
            l0_chatbot,
            mock_ingestion,
            mock_memory,
            chatbot_manager,
        )
        
        # Test delegation
        message = "PDDI개발팀 52주차 주간보고 요약"
        results = list(executor.execute(message, "test-session-001"))
        
        print(f"\n=== L0 -> L1 -> L2 Test ===")
        print(f"Message: {message}")
        print(f"Results: {''.join(results)[:500]}...")
        
        # Verify results contain expected content
        result_text = ''.join(results)
        assert "52주차" in result_text or "주간보고" in result_text, \
            f"Expected weekly report content, got: {result_text[:200]}"
    
    def test_l1_to_l2_delegation(self, chatbot_manager, mock_ingestion, mock_memory):
        """Test: Level 1 -> Level 2 delegation"""
        l1_chatbot = chatbot_manager.get_active("pddi-total")
        assert l1_chatbot is not None
        
        executor = HierarchicalAgentExecutor(
            l1_chatbot,
            mock_ingestion,
            mock_memory,
            chatbot_manager,
        )
        
        message = "52주차 주간보고 요약"
        results = list(executor.execute(message, "test-session-002"))
        
        print(f"\n=== L1 -> L2 Test ===")
        print(f"Message: {message}")
        print(f"Results: {''.join(results)[:500]}...")
        
        result_text = ''.join(results)
        assert "52주차" in result_text, \
            f"Expected 52nd week content, got: {result_text[:200]}"
    
    def test_l2_direct_query(self, chatbot_manager, mock_ingestion, mock_memory):
        """Test: Level 2 direct query"""
        l2_chatbot = chatbot_manager.get_active("rp-pddi-minutes")
        assert l2_chatbot is not None
        
        executor = HierarchicalAgentExecutor(
            l2_chatbot,
            mock_ingestion,
            mock_memory,
            chatbot_manager,
        )
        
        message = "52주차 주간보고 요약"
        results = list(executor.execute(message, "test-session-003"))
        
        print(f"\n=== L2 Direct Test ===")
        print(f"Message: {message}")
        print(f"Results: {''.join(results)[:500]}...")
        
        result_text = ''.join(results)
        assert "52주차" in result_text, \
            f"Expected 52nd week content, got: {result_text[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
