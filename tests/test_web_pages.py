"""
tests/test_web_pages.py - 웹 페이지 E2E 테스트
채팅 페이지 + 관리자 페이지 통합 테스트
"""
import pytest
import requests
import json
from urllib.parse import urlencode

BASE_URL = "http://localhost:8080"
ADMIN_URL = f"{BASE_URL}/admin"


class TestWebPages:
    """웹 페이지 렌더링 및 기능 테스트"""
    
    # ========== 채팅 페이지 테스트 ==========
    
    def test_chat_page_loads(self):
        """TC-WEB-001: 채팅 페이지 정상 로드"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        assert "Multi Custom Agent" in response.text
        assert "chatbot-selector" in response.text
        
    def test_chat_page_with_chatbot_param(self):
        """TC-WEB-002: URL 파라미터로 챗봘 자동 선택"""
        response = requests.get(f"{BASE_URL}/?chatbot=chatbot-hr")
        assert response.status_code == 200
        # HTML에 챗봘 선택 스크립트 포함 확인
        assert "URLSearchParams" in response.text
        assert "chatbot=chatbot-hr" in response.text or "get('chatbot')" in response.text
        
    def test_chat_page_chatbot_list_api(self):
        """TC-WEB-003: 챗봘 목록 API 정상 동작"""
        response = requests.get(f"{BASE_URL}/api/chatbots")
        assert response.status_code == 200
        bots = response.json()
        assert len(bots) > 0
        # chatbot-hr 존재 확인
        hr_bot = [b for b in bots if b['id'] == 'chatbot-hr']
        assert len(hr_bot) == 1
        assert hr_bot[0]['name'] == '인사지원 상위 챗봇'
        
    def test_chat_page_invalid_chatbot_param(self):
        """TC-WEB-004: 잘못된 챗봘 ID 처리"""
        response = requests.get(f"{BASE_URL}/?chatbot=invalid-bot")
        assert response.status_code == 200
        # 에러 메시지 포함 확인
        assert "찾을 수 없습니다" in response.text or "loadChatbots" in response.text
        
    # ========== 관리자 페이지 테스트 ==========
    
    def test_admin_page_loads(self):
        """TC-WEB-005: 관리자 페이지 정상 로드"""
        response = requests.get(ADMIN_URL)
        assert response.status_code == 200
        assert "Agent Store" in response.text
        assert "챗봇 관리자" in response.text
        assert "chatbotGrid" in response.text
        
    def test_admin_page_api_integration(self):
        """TC-WEB-006: 관리자 페이지 API 연동"""
        # 챗봘 목록 API
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        assert response.status_code == 200
        bots = response.json()
        
        # 계층 구조 확인
        parents = [b for b in bots if b['type'] == 'parent']
        children = [b for b in bots if b['type'] == 'child']
        standalone = [b for b in bots if b['type'] == 'standalone']
        
        assert len(parents) >= 3  # chatbot-hr, chatbot-tech, chatbot-c
        assert len(children) >= 7
        assert len(standalone) >= 2
        
    def test_admin_page_stats_api(self):
        """TC-WEB-007: 통계 API 정상 동작"""
        response = requests.get(f"{BASE_URL}/admin/api/stats")
        assert response.status_code == 200
        stats = response.json()
        
        assert "total" in stats
        assert "parents" in stats
        assert "active" in stats
        assert stats['total'] >= 13
        assert stats['parents'] >= 3
        
    # ========== 페이지 간 연동 테스트 ==========
    
    def test_admin_to_chat_navigation(self):
        """TC-WEB-008: 관리자→채팅 페이지 링크"""
        # 관리자 페이지에서 채팅 링크 확인
        response = requests.get(ADMIN_URL)
        assert response.status_code == 200
        
        # 채팅하기 버튼에 있는 URL 패턴 확인
        assert 'href="/?chatbot=' in response.text or "startChat" in response.text
        
    def test_chatbot_types_displayed_correctly(self):
        """TC-WEB-009: 모든 챗봘 유형이 UI에 표시됨"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        bots = response.json()
        
        for bot in bots:
            assert 'type' in bot
            assert bot['type'] in ['parent', 'child', 'standalone']
            
            if bot['type'] == 'parent':
                assert 'sub_chatbots' in bot
                assert len(bot['sub_chatbots']) > 0
            elif bot['type'] == 'child':
                assert 'parent' in bot
                
    def test_parent_child_relationships(self):
        """TC-WEB-010: 상위-하위 관계 정확성"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        bots = response.json()
        
        # chatbot-hr의 하위 챗봘 확인
        hr_bot = [b for b in bots if b['id'] == 'chatbot-hr'][0]
        sub_ids = [s['id'] if isinstance(s, dict) else s for s in hr_bot['sub_chatbots']]
        assert 'chatbot-hr-policy' in sub_ids
        assert 'chatbot-hr-benefit' in sub_ids
        
        # chatbot-hr-policy의 상위가 chatbot-hr인지 확인
        hr_policy = [b for b in bots if b['id'] == 'chatbot-hr-policy'][0]
        assert hr_policy['type'] == 'child'
        assert hr_policy['parent'] == 'chatbot-hr'
        
    # ========== CRUD 테스트 ==========
    
    def test_admin_create_chatbot(self):
        """TC-WEB-011: 챗봘 생성 API"""
        import uuid
        test_id = f"test-bot-{uuid.uuid4().hex[:8]}"
        
        payload = {
            "id": test_id,
            "name": "테스트 챗봇",
            "description": "테스트용 챗봘",
            "type": "standalone",
            "system_prompt": "테스트 프롬프트",
            "db_ids": ["db_new"],
            "active": True
        }
        
        response = requests.post(
            f"{BASE_URL}/admin/api/chatbots",
            json=payload
        )
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'success'
        assert result['id'] == test_id
        
        # 생성 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        created = [b for b in bots if b['id'] == test_id]
        assert len(created) == 1
        
        # 정리
        requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")
        
    def test_admin_create_child_chatbot(self):
        """TC-WEB-012: 하위 챗봘 생성 (상위 Agent에 자동 연결)"""
        import uuid
        test_id = f"test-child-{uuid.uuid4().hex[:8]}"
        
        payload = {
            "id": test_id,
            "name": "테스트 하위 챗봘",
            "description": "상위 Agent의 하위 챗봘",
            "type": "child",
            "parent": "chatbot-hr",
            "system_prompt": "테스트 프롬프트",
            "db_ids": ["db_hr_policy"],
            "active": True
        }
        
        response = requests.post(
            f"{BASE_URL}/admin/api/chatbots",
            json=payload
        )
        assert response.status_code == 200
        
        # chatbot-hr에 하위 챗봘이 추가되었는지 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        hr_bot = [b for b in bots if b['id'] == 'chatbot-hr'][0]
        sub_ids = [s['id'] if isinstance(s, dict) else s for s in hr_bot['sub_chatbots']]
        assert test_id in sub_ids
        
        # 정리
        requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")
        
    def test_admin_delete_chatbot(self):
        """TC-WEB-013: 챗봘 삭제 API"""
        import uuid
        test_id = f"test-delete-{uuid.uuid4().hex[:8]}"
        
        # 생성
        payload = {
            "id": test_id,
            "name": "삭제 테스트",
            "description": "삭제될 챗봘",
            "type": "standalone",
            "system_prompt": "테스트",
            "db_ids": [],
            "active": True
        }
        requests.post(f"{BASE_URL}/admin/api/chatbots", json=payload)
        
        # 삭제
        response = requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")
        assert response.status_code == 200
        
        # 삭제 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        assert test_id not in [b['id'] for b in bots]
        
    def test_admin_delete_removes_from_parent(self):
        """TC-WEB-014: 하위 챗봘 삭제 시 상위 Agent에서도 제거"""
        import uuid
        test_id = f"test-remove-{uuid.uuid4().hex[:8]}"
        
        # 하위 챗봘 생성
        payload = {
            "id": test_id,
            "name": "제거 테스트",
            "description": "상위에서 제거될 챗봘",
            "type": "child",
            "parent": "chatbot-hr",
            "system_prompt": "테스트",
            "db_ids": [],
            "active": True
        }
        requests.post(f"{BASE_URL}/admin/api/chatbots", json=payload)
        
        # 삭제 전 상위 Agent 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        hr_bot = [b for b in bots if b['id'] == 'chatbot-hr'][0]
        sub_ids = [s['id'] if isinstance(s, dict) else s for s in hr_bot['sub_chatbots']]
        assert test_id in sub_ids

        # 삭제
        requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")

        # 상위 Agent에서 제거되었는지 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        hr_bot = [b for b in bots if b['id'] == 'chatbot-hr'][0]
        sub_ids = [s['id'] if isinstance(s, dict) else s for s in hr_bot['sub_chatbots']]
        assert test_id not in sub_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
