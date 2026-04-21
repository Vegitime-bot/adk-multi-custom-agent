#!/usr/bin/env python3
"""세션 자동 연결 테스트 - 간단 버전"""

import requests
import json
import time

BASE_URL = "http://localhost:8080"
CHATBOT_ID = "chatbot-hr"

def test_chat(message: str, session_id: str = None):
    """채팅 API 테스트"""
    payload = {
        "chatbot_id": CHATBOT_ID,
        "message": message,
        "session_id": session_id,
        "mode": "agent"
    }
    
    print(f"\n{'='*60}")
    print(f"Request: '{message}'")
    print(f"Sent session_id: {session_id}")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json=payload,
        stream=True
    )
    
    print(f"Response status: {response.status_code}")
    print("Raw SSE events:")
    print("-" * 60)
    
    received_session_id = None
    event_type = None
    
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            print(f"  {line}")
            
            if line.startswith('event:'):
                event_type = line[7:].strip()
            elif line.startswith('data:'):
                data = line[6:]
                if event_type == 'session':
                    try:
                        # data가 이중 문자열이면 한 번 더 파싱
                        if data.startswith('"') and data.endswith('"'):
                            data = json.loads(data)
                        parsed = json.loads(data) if isinstance(data, str) else data
                        received_session_id = parsed.get('session_id') if isinstance(parsed, dict) else parsed
                        print(f"  -> Parsed session_id: {received_session_id}")
                    except Exception as e:
                        print(f"  -> Parse error: {e}, data={data}")
                elif event_type == 'message':
                    # 첫 메시지만 출력
                    pass
                elif event_type == 'done':
                    break
    
    return received_session_id

def main():
    print("세션 자동 연결 테스트")
    print(f"BASE_URL: {BASE_URL}")
    print(f"CHATBOT_ID: {CHATBOT_ID}")
    
    # 1차 질문
    print("\n[1차 질문]")
    session_id_1 = test_chat("안녕하세요", session_id=None)
    
    time.sleep(1)
    
    # 2차 질문
    print("\n[2차 질문]")
    session_id_2 = test_chat("이전에 무슨 얘기했지?", session_id=None)
    
    # 결과
    print(f"\n{'='*60}")
    print("RESULT:")
    print(f"  1차 session_id: {session_id_1}")
    print(f"  2차 session_id: {session_id_2}")
    if session_id_1 and session_id_1 == session_id_2:
        print("  ✅ SUCCESS: Same session reused!")
    else:
        print("  ❌ FAIL: Different sessions")

if __name__ == "__main__":
    main()
