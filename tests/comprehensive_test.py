#!/usr/bin/env python3
"""
Comprehensive delegation flow tests
"""
import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_chat(chatbot_id, message, description):
    """Test chat and analyze delegation flow"""
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"Chatbot: {chatbot_id} | Message: '{message}'")
    print(f"{'='*70}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={"chatbot_id": chatbot_id, "message": message, "session_id": None},
            stream=True,
            timeout=30
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
        
        # Analyze results
        print("\n📊 분석 결과:")
        print("-" * 70)
        
        # Check delegation indicators
        if "하위 Agent 위임" in full_text:
            print("✅ 하위 Agent 위임 시도됨")
        
        if "전문가 챗봘을 호출" in full_text:
            print("✅ 전문가 호출 단계 진행됨")
            
        if "선택된 전문가" in full_text:
            # Extract selected expert
            import re
            match = re.search(r'선택된 전문가.*?: ([^\n]+)', full_text)
            if match:
                print(f"✅ 선택된 Agent: {match.group(1)}")
        
        if "응답을 종합하는 중" in full_text:
            print("✅ 다중 응답 종합 단계 진행됨")
        
        if "상위 Agent로 위임" in full_text:
            print("⚠️ 상위 Agent로 위임됨 (하위 선택 실패)")
            
        if "적합한 하위 Agent를 찾을 수 없습니다" in full_text:
            print("❌ 하위 Agent 선택 실패")
        
        # Check which sub-chatbot was selected
        if "chatbot-hr-benefit" in full_text or "복리후생" in full_text:
            print("✅ 복리후생 전문가 선택됨")
        elif "chatbot-hr-policy" in full_text or "인사정책" in full_text:
            print("✅ 인사정책 전문가 선택됨")
        
        # Check confidence
        import re
        conf_match = re.search(r'신뢰도:\s*(\d+)%', full_text)
        if conf_match:
            print(f"📈 신뢰도: {conf_match.group(1)}%")
        
        print("\n📝 응답 미리보기:")
        print("-" * 70)
        preview = full_text[:500] + "..." if len(full_text) > 500 else full_text
        print(preview)
        
        return {
            "success": True,
            "delegation_attempted": "하위 Agent 위임" in full_text,
            "expert_selected": "선택된 전문가" in full_text,
            "synthesis_performed": "응답을 종합하는 중" in full_text,
            "delegation_to_parent": "상위 Agent로 위임" in full_text,
            "no_subagent_found": "적합한 하위 Agent를 찾을 수 없습니다" in full_text,
            "full_text": full_text
        }
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return {"success": False, "error": str(e)}


def test_chatbot_config(chatbot_id):
    """Check chatbot configuration"""
    print(f"\n{'='*70}")
    print(f"CONFIG CHECK: {chatbot_id}")
    print(f"{'='*70}")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/chatbots", timeout=10)
        chatbots = resp.json()
        
        cb = next((c for c in chatbots if c['id'] == chatbot_id), None)
        if cb:
            print(f"✅ 챗봇 찾음: {cb['name']}")
            print(f"📋 설정 키: {list(cb.keys())}")
            
            if 'policy' in cb and cb['policy']:
                policy = cb['policy']
                print(f"\n📊 Policy 설정:")
                for k, v in policy.items():
                    print(f"  - {k}: {v}")
            else:
                print("⚠️ Policy 설정 없음")
                
            return cb
        else:
            print(f"❌ 챗봇 {chatbot_id} 찾을 수 없음")
            return None
            
    except Exception as e:
        print(f"❌ 오류: {e}")
        return None


if __name__ == "__main__":
    # Test 1: Config check
    print("🔍 테스트 1: 챗봇 설정 확인")
    test_chatbot_config("chatbot-hr")
    time.sleep(1)
    
    # Test 2: Salary query
    print("\n🔍 테스트 2: 급여 문의")
    test_chat("chatbot-hr", "급여 알려줘", "급여 정보 문의")
    time.sleep(2)
    
    # Test 3: Vacation query  
    print("\n🔍 테스트 3: 연차 문의")
    test_chat("chatbot-hr", "연차 알려줘", "연차 휴가 문의")
    time.sleep(2)
    
    # Test 4: Policy query
    print("\n🔍 테스트 4: 정책 문의")
    test_chat("chatbot-hr", "정책 알려줘", "인사정책 문의")
    time.sleep(2)
    
    # Test 5: Multi-keyword query
    print("\n🔍 테스트 5: 복합 키워드 문의 (급여 + 연차)")
    test_chat("chatbot-hr", "급여랑 연차 알려줘", "복합 문의 - 다중 Agent 선택 예상")
    time.sleep(2)
    
    # Test 6: Parent delegation test
    print("\n🔍 테스트 6: 회사 전체 챗봇에서 HR 문의")
    test_chat("chatbot-company", "인사팀 연락처 알려줘", "상위 챗봘에서 하위로 위임")
    time.sleep(2)
    
    # Test 7: Tech chatbot test
    print("\n🔍 테스트 7: Tech 챗봘에서 백엔드 문의")
    test_chat("chatbot-tech", "백엔드 개발 문의", "기술팀 위임 테스트")
    
    print(f"\n{'='*70}")
    print("✅ 모든 테스트 완료")
    print(f"{'='*70}")
