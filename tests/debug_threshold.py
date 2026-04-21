#!/usr/bin/env python3
"""
Debug: Check actual HYBRID_SCORE_THRESHOLD value at runtime
"""
import sys
sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

import os
print(f"Environment HYBRID_SCORE_THRESHOLD: {os.getenv('HYBRID_SCORE_THRESHOLD', 'not set')}")

from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
print(f"Class HYBRID_SCORE_THRESHOLD: {HierarchicalAgentExecutor.HYBRID_SCORE_THRESHOLD}")

from backend.managers.chatbot_manager import ChatbotManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.managers.memory_manager import MemoryManager

chatbot_mgr = ChatbotManager()
ingestion = IngestionClient()
memory = MemoryManager()

hr_bot = chatbot_mgr.get_active("chatbot-hr")
if hr_bot:
    from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
    executor = HierarchicalAgentExecutor(
        chatbot_def=hr_bot,
        ingestion_client=ingestion,
        memory_manager=memory,
        chatbot_manager=chatbot_mgr,
    )
    print(f"\nInstance threshold check:")
    print(f"  HYBRID_SCORE_THRESHOLD: {executor.HYBRID_SCORE_THRESHOLD}")
    
    # Test selection
    candidates = executor._select_sub_chatbot_hybrid_multi("급여 알려줘")
    print(f"\n  Selected candidates for '급여 알려줘': {len(candidates)}")
    for c in candidates:
        print(f"    - {c[0].id}")
