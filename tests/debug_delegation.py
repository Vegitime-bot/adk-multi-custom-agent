#!/usr/bin/env python3
"""
Debug script for delegation flow issues
"""
import sys
sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

from backend.managers.chatbot_manager import ChatbotManager
from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
from backend.services.embedding_service import get_embedding_service
from backend.retrieval.ingestion_client import IngestionClient
from backend.managers.memory_manager import MemoryManager

def test_delegation_selection():
    """Test sub-agent selection for specific queries"""
    
    # Initialize
    chatbot_mgr = ChatbotManager()
    ingestion = IngestionClient()
    memory = MemoryManager()
    
    # Get chatbot-hr
    hr_bot = chatbot_mgr.get_active("chatbot-hr")
    if not hr_bot:
        print("❌ chatbot-hr not found")
        return
    
    print(f"✅ Found chatbot-hr: {hr_bot.name}")
    print(f"   sub_chatbots: {[s.id for s in hr_bot.sub_chatbots]}")
    print(f"   parent_id: {hr_bot.parent_id}")
    print(f"   level: {hr_bot.level}")
    print()
    
    # Create executor
    executor = HierarchicalAgentExecutor(
        chatbot_def=hr_bot,
        ingestion_client=ingestion,
        memory_manager=memory,
        chatbot_manager=chatbot_mgr,
    )
    
    # Test queries
    test_queries = [
        "급여 알려줘",
        "연차 알려줘",
        "정책 알려줘",
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: '{query}'")
        print("-" * 50)
        
        # Test keyword matching
        message_lower = query.lower()
        for sub_ref in hr_bot.sub_chatbots:
            sub_def = chatbot_mgr.get_active(sub_ref.id)
            if not sub_def:
                continue
            
            keywords = HierarchicalAgentExecutor.KEYWORDS_MAP.get(sub_def.id, [])
            matched = [kw for kw in keywords if kw.lower() in message_lower]
            kw_score = executor._keyword_score(sub_def.id, message_lower)
            
            print(f"  {sub_def.id}:")
            print(f"    keywords: {keywords}")
            print(f"    matched: {matched}")
            print(f"    keyword_score: {kw_score}")
        
        # Test hybrid selection
        candidates = executor._select_sub_chatbot_hybrid_multi(query)
        print(f"\n  Selected candidates: {len(candidates)}")
        for cb, info, scores in candidates:
            print(f"    - {cb.id}: {info}")
        
        if not candidates:
            print("  ⚠️ No candidates selected (threshold too high?)")
            
            # Show all scores without threshold
            print("\n  All scores (without threshold):")
            for sub_ref in hr_bot.sub_chatbots:
                sub_def = chatbot_mgr.get_active(sub_ref.id)
                if not sub_def:
                    continue
                kw = executor._keyword_score(sub_def.id, message_lower)
                emb = executor._embedding_score(query, sub_def)
                hybrid = 0.4 * kw + 0.6 * emb
                print(f"    {sub_def.id}: kw={kw:.3f}, emb={emb:.3f}, hybrid={hybrid:.3f}")


if __name__ == "__main__":
    test_delegation_selection()
