#!/usr/bin/env python3
"""
Test delegation flow after server restart
"""
import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_chat(chatbot_id, message):
    """Test chat with a chatbot"""
    print(f"\n{'='*60}")
    print(f"Query: '{message}' to {chatbot_id}")
    print(f"{'='*60}")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "chatbot_id": chatbot_id,
            "message": message,
            "session_id": None
        },
        stream=True
    )
    
    print("Response:")
    full_text = ""
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data:'):
                try:
                    data = json.loads(line[5:].strip())
                    if isinstance(data, str):
                        print(data, end='', flush=True)
                        full_text += data
                except:
                    pass
    print("\n")
    
    # Check delegation flow
    if "→" in full_text:
        print("✅ Delegation occurred")
    elif "하위 Agent" in full_text and "없습니다" in full_text:
        print("❌ No sub-agent found")
    else:
        print("ℹ️ Direct response or no delegation")
    
    return full_text

if __name__ == "__main__":
    # Test cases
    test_chat("chatbot-hr", "급여 알려줘")
    time.sleep(1)
    
    test_chat("chatbot-hr", "연차 알려줘")
    time.sleep(1)
    
    test_chat("chatbot-hr", "정책 알려줘")
