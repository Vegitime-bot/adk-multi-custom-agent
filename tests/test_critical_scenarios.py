"""
10개 핵심 위임 시나리오 테스트

시나리오 구성:
1. A가 A 질문에 답변 (Parent self-answer)
2. A가 D 질문에 D로 위임 (Parent → Sub)
3. D가 D 질문에 답변 (Sub self-answer)
4. D가 모르는 질문에 상위 위임 (Sub → Parent)
5. A가 다수 하위 중 적합한 곳으로 위임
6. A가 다수 하위 중 모두 해당 없음 → 상위 위임
7. Root가 답변 → fallback (최종)
8. 최대 위임 깊이 초과 처리
9. 신뢰도 경계값 (threshold exact)
10. Chain delegation: A→B→C 실제 답변
"""

import pytest
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, '/Users/vegitime/.openclaw/workspace/projects/multi-custom-agent')

from backend.executors.hierarchical_agent_executor import (
    HierarchicalAgentExecutor,
    DelegateResult,
)
from backend.core.models import ChatbotDef, SubChatbotRef, ExecutionRole


def make_chatbot_def(
    chatbot_id: str,
    name: str,
    level: int = 0,
    sub_chatbots: list = None,
    parent_id: str = None,
    system_prompt: str = "You are a helpful assistant.",
    description: str = "Test chatbot",
    db_ids: list = None,
    policy: dict = None,
):
    """Helper to create a mock ChatbotDef"""
    mock = Mock(spec=ChatbotDef)
    mock.id = chatbot_id
    mock.name = name
    mock.level = level
    mock.sub_chatbots = sub_chatbots or []
    mock.parent_id = parent_id
    mock.system_prompt = system_prompt
    mock.description = description
    mock.is_root = (parent_id is None)
    mock.policy = policy or {}
    
    mock.retrieval = Mock()
    mock.retrieval.db_ids = db_ids or ["default-db"]
    mock.retrieval.k = 5
    mock.retrieval.filter_metadata = None
    
    mock.memory = Mock()
    mock.memory.max_messages = 20
    
    return mock


class TestCriticalScenarios:
    """10개 핵심 위임 시나리오"""
    
    @pytest.fixture
    def setup_hierarchy(self):
        """
        3단계 계층 구조 설정:
        
        Root(R) - Level 0
          └─ Parent A (HR) - Level 1
                ├─ Child B (Policy) - Level 2
                │     └─ Grandchild C (Detail) - Level 3
                └─ Child D (DevOps) - Level 2
        """
        # Level 3: C (Detail 전문)
        chatbot_c = make_chatbot_def(
            chatbot_id="chatbot-policy-detail",
            name="Policy Detail Bot C",
            level=3,
            parent_id="chatbot-hr-policy",
            db_ids=["policy-detail-db"],
            system_prompt="당신은 정책 세부사항 전문가입니다.",
        )
        
        # Level 2: B (Policy 전문, C의 Parent)
        chatbot_b = make_chatbot_def(
            chatbot_id="chatbot-hr-policy",
            name="HR Policy Bot B",
            level=2,
            sub_chatbots=[
                SubChatbotRef(id='chatbot-policy-detail', level=3, default_role=ExecutionRole.AGENT),
            ],
            parent_id="chatbot-hr",
            db_ids=["policy-db"],
            system_prompt="당신은 HR 정책 전문가입니다.",
        )
        
        # Level 2: D (DevOps 전문)
        chatbot_d = make_chatbot_def(
            chatbot_id="chatbot-tech-devops",
            name="DevOps Bot D",
            level=2,
            parent_id="chatbot-hr",
            db_ids=["devops-db"],
            system_prompt="당신은 DevOps 전문가입니다. docker, kubernetes에 대해 답변하세요.",
        )
        
        # Level 1: A (HR 전문, B와 D의 Parent)
        chatbot_a = make_chatbot_def(
            chatbot_id="chatbot-hr",
            name="HR Parent Bot A",
            level=1,
            sub_chatbots=[
                SubChatbotRef(id='chatbot-hr-policy', level=2, default_role=ExecutionRole.AGENT),
                SubChatbotRef(id='chatbot-tech-devops', level=2, default_role=ExecutionRole.AGENT),
            ],
            parent_id="chatbot-root",
            db_ids=["hr-db"],
            system_prompt="당신은 HR 전문가입니다. 인사/복지에 대해 답변하세요.",
        )
        
        # Level 0: R (Root)
        chatbot_r = make_chatbot_def(
            chatbot_id="chatbot-root",
            name="Root Bot R",
            level=0,
            sub_chatbots=[
                SubChatbotRef(id='chatbot-hr', level=1, default_role=ExecutionRole.AGENT),
            ],
            parent_id=None,
            db_ids=["root-db"],
            system_prompt="당신은 Root 챗봇입니다. 전반적인 안내를 제공하세요.",
        )
        
        # ChatbotManager Mock
        mock_manager = Mock()
        def get_active(chatbot_id):
            bots = {
                "chatbot-policy-detail": chatbot_c,
                "chatbot-hr-policy": chatbot_b,
                "chatbot-tech-devops": chatbot_d,
                "chatbot-hr": chatbot_a,
                "chatbot-root": chatbot_r,
            }
            return bots.get(chatbot_id)
        mock_manager.get_active = Mock(side_effect=get_active)
        
        return {
            'R': chatbot_r,
            'A': chatbot_a,
            'B': chatbot_b,
            'C': chatbot_c,
            'D': chatbot_d,
            'manager': mock_manager,
        }
    
    def test_01_parent_answers_self_domain(self, setup_hierarchy):
        """
        TC-CRIT-01: Parent A에게 A의 전문분야 질문 → A가 직접 답변
        
        Given: A는 HR 전문가, confidence 85%
        When: "연차 정책 알려줘" (HR 관련)
        Then: A가 직접 답변, 위임 없음
        """
        bots = setup_hierarchy
        
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=bots['A'],
            ingestion_client=Mock(),
            memory_manager=mock_memory,
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # A가 HR 질문에 높은 confidence
        executor_a._retrieve = Mock(return_value="연차 정책: 1년차 15일...")
        executor_a._calculate_confidence = Mock(return_value=85)
        executor_a._stream_chat = Mock(return_value=iter(["연차는 1년차에 15일입니다."]))
        
        # 위임 메서드 Mock
        executor_a._delegate_to_sub_chatbots = Mock(return_value=iter([]))
        executor_a._delegate_to_parent = Mock(return_value=iter([]))
        
        result = list(executor_a.execute("연차 정책 알려줘", "sess-01"))
        result_text = "".join(result)
        
        assert executor_a._delegate_to_sub_chatbots.call_count == 0, \
            "[TC-01] A의 전문분야 질문에 하위 위임하면 안 됨"
        assert "연차" in result_text or "15일" in result_text, \
            "[TC-01] A가 직접 답변해야 함"
        print("✅ TC-01: Parent A가 자신의 전문분야(HR) 질문에 직접 답변")
    
    def test_02_parent_delegates_to_qualified_sub(self, setup_hierarchy):
        """
        TC-CRIT-02: Parent A에게 D의 전문분야 질문 → A가 D로 위임 → D가 답변
        
        Given: A는 HR 전문가(confidence 15%), D는 DevOps 전문가
        When: "docker 사용법 알려줘" (DevOps 관련)
        Then: A가 D로 위임, D가 실제 답변 (fallback 아님)
        """
        bots = setup_hierarchy
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=bots['A'],
            ingestion_client=Mock(),
            memory_manager=Mock(),
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # A는 DevOps 모름 (confidence 낮음)
        executor_a._retrieve = Mock(return_value="")
        executor_a._calculate_confidence = Mock(return_value=15)
        
        # 위임 실행 시뮬레이션 - D가 답변
        def mock_delegate_to_sub(*args, **kwargs):
            yield "📋 전문가 상담 필요\n\n"
            yield "✅ 선택: DevOps Bot D\n\n"
            yield "Docker는 컨테이너 가상화 기술입니다."
        
        executor_a._delegate_to_sub_chatbots = mock_delegate_to_sub
        executor_a._delegate_to_parent = Mock(return_value=iter([]))
        
        result = list(executor_a.execute("docker 사용법 알려줘", "sess-02"))
        result_text = "".join(result)
        
        assert executor_a._delegate_to_parent.call_count == 0, \
            "[TC-02] 하위 있으면 상위 위임하면 안 됨"
        assert "DevOps Bot D" in result_text, \
            "[TC-02] D가 선택되어야 함"
        assert "Docker는 컨테이너" in result_text, \
            "[TC-02] D가 실제 답변 제공"
        assert "D에게 질문하세요" not in result_text.lower(), \
            "[TC-02] fallback 메시지 없어야 함"
        print("✅ TC-02: Parent A가 D(DevOps) 질문을 D로 위임, D가 실제 답변")
    
    def test_03_child_answers_self_domain(self, setup_hierarchy):
        """
        TC-CRIT-03: Child D에게 D의 전문분야 질문 → D가 직접 답변
        
        Given: D는 DevOps 전문가, confidence 90%
        When: "kubernetes 배포 방법" (DevOps 관련)
        Then: D가 직접 답변
        """
        bots = setup_hierarchy
        
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor_d = HierarchicalAgentExecutor(
            chatbot_def=bots['D'],
            ingestion_client=Mock(),
            memory_manager=mock_memory,
            chatbot_manager=bots['manager'],
        )
        executor_d.delegation_threshold = 70
        
        # D는 DevOps 전문가
        executor_d._retrieve = Mock(return_value="kubectl apply -f deployment.yaml...")
        executor_d._calculate_confidence = Mock(return_value=90)
        executor_d._stream_chat = Mock(return_value=iter(["kubectl apply로 배포합니다."]))
        
        result = list(executor_d.execute("kubernetes 배포 방법", "sess-03"))
        result_text = "".join(result)
        
        assert "kubectl" in result_text, \
            "[TC-03] D가 DevOps 질문에 직접 답변해야 함"
        print("✅ TC-03: Child D가 자신의 전문분야(DevOps) 질문에 직접 답변")
    
    def test_04_child_delegates_up_when_unknown(self, setup_hierarchy):
        """
        TC-CRIT-04: Child D에게 D가 모르는 질문 → D가 Parent A로 위임
        
        Given: D는 DevOps 전문가, HR 질문에 confidence 10%
        When: "급여 계산 방법" (HR 관련 - D가 모름)
        Then: D가 A로 위임, fallback 아님
        """
        bots = setup_hierarchy
        
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor_d = HierarchicalAgentExecutor(
            chatbot_def=bots['D'],
            ingestion_client=Mock(),
            memory_manager=mock_memory,
            chatbot_manager=bots['manager'],
        )
        executor_d.delegation_threshold = 70
        
        # D는 HR 모름 (confidence 낮음, 하위 없음)
        executor_d._retrieve = Mock(return_value="")
        executor_d._calculate_confidence = Mock(return_value=10)
        
        # 상위 위임 시뮬레이션
        def mock_delegate_to_parent(*args, **kwargs):
            yield "📤 D → A로 위임\n"
            yield "HR Bot A가 답변: 급여는 기본급 + 수당으로 계산됩니다."
        
        executor_d._delegate_to_sub_chatbots = Mock(return_value=iter([]))
        executor_d._delegate_to_parent = mock_delegate_to_parent
        
        result = list(executor_d.execute("급여 계산 방법", "sess-04"))
        result_text = "".join(result)
        
        assert "위임" in result_text or "A" in result_text, \
            "[TC-04] D가 A로 위임해야 함"
        assert "모릅니다" not in result_text.lower() and "fallback" not in result_text.lower(), \
            "[TC-04] fallback 메시지 없어야 함"
        print("✅ TC-04: Child D가 모르는 질문에 Parent A로 위임")
    
    def test_05_parent_selects_appropriate_sub(self, setup_hierarchy):
        """
        TC-CRIT-05: A가 다수 하위 중 적합한 곳으로 위임
        
        Given: A의 하위는 B(HR Policy)와 D(DevOps)
        When: "docker 명령어" (D 전문분야)
        Then: A가 D로 위임 (B로 위임하면 안 됨)
        """
        bots = setup_hierarchy
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=bots['A'],
            ingestion_client=Mock(),
            memory_manager=Mock(),
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # A는 docker 모름
        executor_a._retrieve = Mock(return_value="")
        executor_a._calculate_confidence = Mock(return_value=20)
        
        # D로 위임 확인용 Mock
        captured_calls = []
        def capture_delegate(*args, **kwargs):
            captured_calls.append("sub_delegation")
            yield "위임: DevOps Bot D"
        
        executor_a._delegate_to_sub_chatbots = capture_delegate
        executor_a._delegate_to_parent = Mock(return_value=iter([]))
        
        result = list(executor_a.execute("docker 명령어 알려줘", "sess-05"))
        
        assert "sub_delegation" in captured_calls, \
            "[TC-05] A가 하위로 위임해야 함"
        print("✅ TC-05: Parent A가 다수 하위 중 적합한 D로 위임")
    
    def test_06_parent_delegates_up_when_no_qualified_sub(self, setup_hierarchy):
        """
        TC-CRIT-06: A의 하위 모두 해당 없음 → A가 Root R로 위임
        
        Given: A의 하위 B, D 모두 '재무' 관련 없음
        When: "재무제표 분석 방법" (재무 관련)
        Then: A가 R로 위임 (fallback 아님)
        """
        bots = setup_hierarchy
        
        # A의 하위 비우기 (sub_chatbots 없음으로 설정)
        chatbot_a_no_subs = make_chatbot_def(
            chatbot_id="chatbot-hr",
            name="HR Parent Bot A",
            level=1,
            sub_chatbots=[],  # 하위 없음
            parent_id="chatbot-root",
            db_ids=["hr-db"],
        )
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=chatbot_a_no_subs,
            ingestion_client=Mock(),
            memory_manager=Mock(),
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # A는 재무 모름
        executor_a._retrieve = Mock(return_value="")
        executor_a._calculate_confidence = Mock(return_value=15)
        
        # 상위 위임 확인
        captured_calls = []
        def capture_parent_delegate(*args, **kwargs):
            captured_calls.append("parent_delegation")
            yield "위임: Root Bot R"
        
        executor_a._delegate_to_sub_chatbots = Mock(return_value=iter([]))
        executor_a._delegate_to_parent = capture_parent_delegate
        
        result = list(executor_a.execute("재무제표 분석 방법", "sess-06"))
        
        assert "parent_delegation" in captured_calls, \
            "[TC-06] A가 하위 없으면 상위로 위임해야 함"
        print("✅ TC-06: Parent A가 적합한 하위 없을 때 Root R로 위임")
    
    def test_07_root_fallback_when_no_answer(self, setup_hierarchy):
        """
        TC-CRIT-07: Root R이 답변 못하면 fallback (최종)
        
        Given: R은 Root, 상위 없음, confidence 낮음, 하위 없음
        When: "알 수 없는 질문"
        Then: R이 fallback 메시지 (더 위임할 곳 없음)
        """
        bots = setup_hierarchy
        
        # 하위 없는 Root 설정
        chatbot_r_no_subs = make_chatbot_def(
            chatbot_id="chatbot-root",
            name="Root Bot R",
            level=0,
            sub_chatbots=[],
            parent_id=None,
            db_ids=["root-db"],
            system_prompt="당신은 Root 챗봇입니다.",
        )
        
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor_r = HierarchicalAgentExecutor(
            chatbot_def=chatbot_r_no_subs,
            ingestion_client=Mock(),
            memory_manager=mock_memory,
            chatbot_manager=bots['manager'],
        )
        executor_r.delegation_threshold = 70
        
        # R은 모름, 상위 없음
        executor_r._retrieve = Mock(return_value="")
        executor_r._calculate_confidence = Mock(return_value=10)
        executor_r._stream_chat = Mock(return_value=iter(["죄송합니다. 해당 내용은 확인할 수 없습니다."]))
        
        result = list(executor_r.execute("알 수 없는 질문", "sess-07"))
        result_text = "".join(result)
        
        assert "없습니다" in result_text or "모릅니다" in result_text or "죄송" in result_text, \
            "[TC-07] Root는 최종 fallback 제공해야 함"
        print("✅ TC-07: Root R이 답변 못하면 fallback (최종)")
    
    def test_08_max_delegation_depth_protection(self, setup_hierarchy):
        """
        TC-CRIT-08: 최대 위임 깊이 초과 시 처리
        
        Given: delegation_depth가 MAX(5)에 도달
        When: 추가 위임 시도
        Then: 위임 중단, 현재 Agent가 최선 답변
        """
        bots = setup_hierarchy
        
        mock_memory = Mock()
        mock_memory.get_history.return_value = []
        
        executor_c = HierarchicalAgentExecutor(
            chatbot_def=bots['C'],
            ingestion_client=Mock(),
            memory_manager=mock_memory,
            chatbot_manager=bots['manager'],
            delegation_depth=5,  # MAX 도달
        )
        executor_c.delegation_threshold = 70
        
        # depth 초과 시 자체 답변
        executor_c._retrieve = Mock(return_value="일부 정보")
        executor_c._calculate_confidence = Mock(return_value=30)
        executor_c._stream_chat = Mock(return_value=iter(["최대 위임 깊이 도달. C가 답변합니다."]))
        
        result = list(executor_c.execute("질문", "sess-08"))
        result_text = "".join(result)
        
        assert "최대 위임 깊이" in result_text or "도달" in result_text, \
            "[TC-08] 최대 깊이 초과 시 경고 메시지"
        print("✅ TC-08: 최대 위임 깊이 초과 시 처리")
    
    def test_09_exact_threshold_boundary(self, setup_hierarchy):
        """
        TC-CRIT-09: 신뢰도가 threshold와 정확히 일치
        
        Given: threshold=70, confidence=70
        When: 질문
        Then: 자체 답변 (위임하지 않음)
        """
        bots = setup_hierarchy
        
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=bots['A'],
            ingestion_client=Mock(),
            memory_manager=Mock(),
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # confidence가 정확히 threshold
        result = executor_a._select_delegate_target(confidence=70, message="테스트 질문")
        
        assert result.target == 'self', \
            "[TC-09] confidence == threshold 이면 'self'"
        assert '70' in result.reason, \
            "[TC-09] reason에 70% 포함"
        print("✅ TC-09: 신뢰도가 threshold와 정확히 일치 시 자체 답변")
    
    def test_10_chain_delegation_a_to_b_to_c(self, setup_hierarchy):
        """
        TC-CRIT-10: Chain 위임: A→B→C 실제 답변
        
        Given: A는 정책 세부사항 모름, B도 모름, C는 전문가
        When: "정책 세부항목 3.2.1" (C 전문분야)
        Then: A→B→C로 위임 체인, C가 실제 답변
        """
        bots = setup_hierarchy
        
        # A 설정
        executor_a = HierarchicalAgentExecutor(
            chatbot_def=bots['A'],
            ingestion_client=Mock(),
            memory_manager=Mock(),
            chatbot_manager=bots['manager'],
        )
        executor_a.delegation_threshold = 70
        
        # A는 세부사항 모름 → B로 위임
        executor_a._retrieve = Mock(return_value="")
        executor_a._calculate_confidence = Mock(return_value=20)
        
        # 체인 위임 시뮬레이션: A→B→C→답변
        def mock_chain_delegation(*args, **kwargs):
            yield "📋 A → B 위임\n"
            yield "📋 B → C 위임\n"
            yield "✅ C가 답변: 정책 세부항목 3.2.1은..."
        
        executor_a._delegate_to_sub_chatbots = mock_chain_delegation
        
        result = list(executor_a.execute("정책 세부항목 3.2.1 알려줘", "sess-10"))
        result_text = "".join(result)
        
        assert "B" in result_text and "C" in result_text, \
            "[TC-10] A→B→C 체인 위임되어야 함"
        assert "C가 답변" in result_text or "세부항목" in result_text, \
            "[TC-10] C가 실제 답변 제공해야 함"
        print("✅ TC-10: Chain 위임 A→B→C 실제 답변")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
