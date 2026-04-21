"""
tests/test_admin_panel.py - 관리자 페이지 통합 테스트
"""
import pytest
import requests
import json

BASE_URL = "http://localhost:8080"
ADMIN_URL = f"{BASE_URL}/admin"


class TestAdminPanel:
    """관리자 페이지 UI + 기능 통합 테스트"""
    
    # ========== 페이지 로드 테스트 ==========
    
    def test_admin_page_structure(self):
        """TC-ADMIN-001: 관리자 페이지 구조 확인"""
        response = requests.get(ADMIN_URL)
        assert response.status_code == 200
        
        html = response.text
        # 필수 요소 확인
        assert "Agent Store" in html, "로고 누락"
        assert "chatbotGrid" in html, "챗봘 그리드 누락"
        assert "searchInput" in html, "검색 입력 누락"
        assert "chatbotModal" in html, "생성 모달 누락"
        assert "nav-menu" in html, "사이드바 네비게이션 누락"
        
    def test_admin_sidebar_navigation(self):
        """TC-ADMIN-002: 사이드바 네비게이션 존재 확인"""
        response = requests.get(ADMIN_URL)
        html = response.text
        
        # 4개 탭 확인
        assert 'data-view="store"' in html, "스토어 탭 누락"
        assert 'data-view="hierarchy"' in html, "계층 탭 누락"
        assert 'data-view="users"' in html, "사용자 탭 누락"
        assert 'data-view="settings"' in html, "설정 탭 누락"
        
    def test_admin_css_loaded(self):
        """TC-ADMIN-003: CSS 파일 로드 확인"""
        response = requests.get(f"{BASE_URL}/static/admin/style.css")
        assert response.status_code == 200
        assert ".chatbot-card" in response.text
        assert ".sidebar" in response.text
        
    def test_admin_js_loaded(self):
        """TC-ADMIN-004: JS 파일 로드 확인"""
        response = requests.get(f"{BASE_URL}/static/admin/app.js")
        assert response.status_code == 200
        assert "loadChatbots" in response.text
        assert "createCardHTML" in response.text
        
    # ========== 챗봘 관리 기능 테스트 ==========
    
    def test_chatbot_list_api_integration(self):
        """TC-ADMIN-005: 챗봘 목록 API 연동"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        assert response.status_code == 200
        
        bots = response.json()
        assert len(bots) > 0
        
        # 필수 필드 확인
        for bot in bots:
            assert "id" in bot
            assert "name" in bot
            assert "type" in bot
            assert bot["type"] in ["parent", "child", "standalone"]
            
    def test_chatbot_card_data_structure(self):
        """TC-ADMIN-006: 카드 데이터 구조 검증"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        bots = response.json()
        
        for bot in bots:
            # 모든 챗봘에 기본 필드
            assert isinstance(bot["id"], str)
            assert isinstance(bot["name"], str)
            assert isinstance(bot["description"], str)
            assert isinstance(bot["active"], bool)
            assert isinstance(bot["db_ids"], list)
            assert isinstance(bot["sub_chatbots"], list)
            
            # 타입별 필드
            if bot["type"] == "parent":
                assert len(bot["sub_chatbots"]) >= 0
            elif bot["type"] == "child":
                assert "parent" in bot
                assert isinstance(bot["parent"], str)
                
    def test_chatbot_type_distribution(self):
        """TC-ADMIN-007: 챗봘 유형 분포 확인"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        bots = response.json()
        
        parents = [b for b in bots if b["type"] == "parent"]
        children = [b for b in bots if b["type"] == "child"]
        standalone = [b for b in bots if b["type"] == "standalone"]
        
        # 최소 3개 parent, 1개 child, 1개 standalone 확인
        assert len(parents) >= 3, f"parent 챗봘 부족: {len(parents)}개"
        assert len(children) >= 1, f"child 챗봘 부족: {len(children)}개"
        assert len(standalone) >= 1, f"standalone 챗봘 부족: {len(standalone)}개"
        
    # ========== CRUD 기능 테스트 ==========
    
    def test_chatbot_create_modal_fields(self):
        """TC-ADMIN-008: 생성 모달 필드 존재 확인"""
        response = requests.get(ADMIN_URL)
        html = response.text
        
        # 필수 입력 필드
        assert 'id="chatbotId"' in html
        assert 'id="chatbotName"' in html
        assert 'id="chatbotDesc"' in html
        assert 'id="chatbotType"' in html
        assert 'id="systemPrompt"' in html
        assert 'id="parentSelectGroup"' in html
        
    def test_chatbot_create_api(self):
        """TC-ADMIN-009: 챗봘 생성 API"""
        import uuid
        test_id = f"admin-test-{uuid.uuid4().hex[:8]}"
        
        payload = {
            "id": test_id,
            "name": "관리자 테스트 챗봘",
            "description": "테스트용",
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
        assert result["status"] == "success"
        assert result["id"] == test_id
        
        # 정리
        requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")
        
    def test_chatbot_delete_api(self):
        """TC-ADMIN-010: 챗봘 삭제 API"""
        import uuid
        test_id = f"delete-test-{uuid.uuid4().hex[:8]}"
        
        # 생성
        payload = {
            "id": test_id,
            "name": "삭제 테스트",
            "description": "삭제될 챗봘",
            "type": "standalone",
            "system_prompt": "test",
            "db_ids": [],
            "active": True
        }
        requests.post(f"{BASE_URL}/admin/api/chatbots", json=payload)
        
        # 삭제
        response = requests.delete(f"{BASE_URL}/admin/api/chatbots/{test_id}")
        assert response.status_code == 200
        
        result = response.json()
        assert result["status"] == "success"
        
        # 삭제 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        assert test_id not in [b["id"] for b in bots]
        
    def test_chatbot_hierarchy_on_create(self):
        """TC-ADMIN-011: 하위 Agent 생성 시 상위 연결"""
        import uuid
        child_id = f"hierarchy-test-{uuid.uuid4().hex[:8]}"
        
        payload = {
            "id": child_id,
            "name": "하위 테스트 챗봘",
            "description": "상위 Agent 테스트",
            "type": "child",
            "parent": "chatbot-hr",
            "system_prompt": "test",
            "db_ids": [],
            "active": True
        }
        
        response = requests.post(f"{BASE_URL}/admin/api/chatbots", json=payload)
        assert response.status_code == 200
        
        # 상위 Agent에 하위 추가되었는지 확인
        bots = requests.get(f"{BASE_URL}/admin/api/chatbots").json()
        hr_bot = [b for b in bots if b["id"] == "chatbot-hr"][0]
        sub_ids = [s['id'] if isinstance(s, dict) else s for s in hr_bot["sub_chatbots"]]
        assert child_id in sub_ids
        
        # 정리
        requests.delete(f"{BASE_URL}/admin/api/chatbots/{child_id}")
        
    # ========== 통계 기능 테스트 ==========
    
    def test_stats_api(self):
        """TC-ADMIN-012: 통계 API"""
        response = requests.get(f"{BASE_URL}/admin/api/stats")
        assert response.status_code == 200
        
        stats = response.json()
        assert "total" in stats
        assert "parents" in stats
        assert "active" in stats
        assert stats["total"] >= 13
        assert stats["parents"] >= 3
        
    # ========== 채팅 연동 테스트 ==========
    
    def test_chat_link_integration(self):
        """TC-ADMIN-013: 채팅 페이지 연동"""
        response = requests.get(ADMIN_URL)
        html = response.text
        
        # 채팅 링크 패턴 확인
        assert 'href="/?chatbot=' in html or "startChat" in html or "/chat/" in html
        
    def test_chat_link_url_format(self):
        """TC-ADMIN-014: 채팅 링크 URL 형식"""
        response = requests.get(f"{BASE_URL}/admin/api/chatbots")
        bots = response.json()
        
        # 각 챗봘에 대해 채팅 URL 생성 가능
        for bot in bots:
            chat_url = f"{BASE_URL}/?chatbot={bot['id']}"
            resp = requests.get(chat_url, allow_redirects=False)
            assert resp.status_code in [200, 302], f"채팅 URL 오류: {chat_url}"
            
    # ========== 검색 및 필터 테스트 ==========
    
    def test_search_functionality(self):
        """TC-ADMIN-015: 검색 기능 (프론트엔드)"""
        response = requests.get(ADMIN_URL)
        html = response.text
        
        # 검색 입력 필드 존재
        assert 'id="searchInput"' in html
        # placeholder 확인
        assert "챗봘 검색" in html
        
    def test_filter_tabs_structure(self):
        """TC-ADMIN-016: 필터 탭 구조"""
        response = requests.get(ADMIN_URL)
        html = response.text
        
        # 4개 필터 버튼
        assert 'data-filter="all"' in html
        assert 'data-filter="parent"' in html
        assert 'data-filter="child"' in html
        assert 'data-filter="standalone"' in html
        
    # ========== 에러 처리 테스트 ==========
    
    def test_404_error_handling(self):
        """TC-ADMIN-017: 존재하지 않는 챗봘 삭제"""
        response = requests.delete(f"{BASE_URL}/admin/api/chatbots/non-existent-99999")
        assert response.status_code == 404
        
    def test_invalid_chatbot_id_create(self):
        """TC-ADMIN-018: 중복 ID로 생성 시도"""
        # 이미 존재하는 ID로 생성 시도
        payload = {
            "id": "chatbot-hr",  # 이미 존재하는 ID
            "name": "테스트",
            "description": "",
            "type": "standalone",
            "system_prompt": "",
            "db_ids": [],
            "active": True
        }
        
        response = requests.post(f"{BASE_URL}/admin/api/chatbots", json=payload)
        # 중복 ID는 400 오류 예상
        assert response.status_code == 400
        
    # ========== 권한 통합 테스트 ==========
    
    def test_admin_permissions_api_link(self):
        """TC-ADMIN-019: 권한 API 연동 확인"""
        # 권한 API가 존재하는지 확인
        response = requests.get(f"{BASE_URL}/api/permissions/users/user-001")
        assert response.status_code == 200
        
        data = response.json()
        assert "knox_id" in data
        assert "permissions" in data
        assert "total" in data
        
    def test_stats_permissions_integrated(self):
        """TC-ADMIN-020: 통계-권한 통합"""
        # 관리자 권한 통계
        response = requests.get(f"{BASE_URL}/api/permissions/admin/stats")
        assert response.status_code == 200
        
        stats = response.json()
        assert "total_permissions" in stats
        assert "unique_users" in stats
        assert "unique_chatbots" in stats
        

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
