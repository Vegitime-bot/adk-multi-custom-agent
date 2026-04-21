#!/usr/bin/env python3
"""
Debug: Test delegation through actual API vs local executor
"""
import sys
sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

import requests
import json

BASE_URL = "http://localhost:8080"

def test_via_api():
    """Test via actual API call"""
    print("=== Testing via API ===")
    
    # First check chatbot-hr config
    resp = requests.get(f"{BASE_URL}/api/chatbots")
    chatbots = resp.json()
    
    hr = next((c for c in chatbots if c['id'] == 'chatbot-hr'), None)
    if hr:
        print(f"\nchatbot-hr config:")
        print(f"  name: {hr.get('name')}")
        print(f"  policy: {json.dumps(hr.get('policy', {}), indent=2)}")
        print(f"  sub_chatbots: {[s.get('id') for s in hr.get('sub_chatbots', [])]}")
    
    # Test chat
    print(f"\n=== Sending '급여 알려줘' to chatbot-hr ===")
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={"chatbot_id": "chatbot-hr", "message": "급여 알려줘", "session_id": None},
        stream=True
    )
    
    full_text = ""
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data:'):
                try:
                    data = json.loads(line[5:].strip())
                    if isinstance(data, str):
                        full_text += data
                except:
                    pass
    
    print(full_text)
    
    # Check if sub-agent was selected
    if "전문가 챗봇을 호출합니다" in full_text:
        if "❌ 적합한 하위 Agent" in full_text:
            print("\n❌ No sub-agent selected")
        elif "→" in full_text and ("hr-benefit" in full_text or "hr-policy" in full_text):
            print("\n✅ Sub-agent selected")
        else:
            print("\n⚠️ Unclear delegation")


def test_local():
    """Test via local executor"""
    print("\n\n=== Testing via Local Executor ===")
    
    from backend.managers.chatbot_manager import ChatbotManager
    from backend.executors.hierarchical_agent_executor import HierarchicalAgentExecutor
    from backend.retrieval.ingestion_client import IngestionClient
    from backend.managers.memory_manager import MemoryManager
    
    chatbot_mgr = ChatbotManager()
    ingestion = IngestionClient()
    memory = MemoryManager()
    
    hr_bot = chatbot_mgr.get_active("chatbot-hr")
    if not hr_bot:
        print("❌ chatbot-hr not found")
        return
    
    print(f"\nLocal chatbot-hr config:")
    print(f"  name: {hr_bot.name}")
    print(f"  policy.hybrid_score_threshold: {hr_bot.policy.get('hybrid_score_threshold', 'not set')}")
    print(f"  sub_chatbots: {[s.id for s in hr_bot.sub_chatbots]}")
    
    executor = HierarchicalAgentExecutor(
        chatbot_def=hr_bot,
        ingestion_client=ingestion,
        memory_manager=memory,
        chatbot_manager=chatbot_mgr,
    )
    
    print(f"\n  Executor hybrid_score_threshold: {executor.hybrid_score_threshold}")
    
    # Test selection
    candidates = executor._select_sub_chatbot_hybrid_multi("급여 알려줘")
    print(f"\n  Selected candidates: {len(candidates)}")
    for c in candidates:
        print(f"    - {c[0].id}: {c[1]}")


if __name__ == "__main__":
    test_via_api()
    test_local()
