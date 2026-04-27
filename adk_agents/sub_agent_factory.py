"""
SubAgentFactory - JSON 정의를 ADK Agent로 변환하는 팩토리
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

from backend.debug_logger import logger

# ADK import
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    ADK_AVAILABLE = True
except ImportError as e:
    ADK_AVAILABLE = False
    logger.error(f"[SubAgentFactory] ADK not available: {e}")

from adk_agents.tools.delegation_tools import calculate_confidence, select_sub_chatbot, should_delegate


class SubAgentFactory:
    """JSON 챗봇 정의를 ADK Agent로 변환하는 팩토리"""
    
    def __init__(self, model=None):
        if not ADK_AVAILABLE:
            raise RuntimeError("ADK not available")
        
        self.model = model or self._get_default_model()
        self._agent_cache: Dict[str, Agent] = {}
        logger.info("[SubAgentFactory] Initialized")
    
    def _get_default_model(self) -> LiteLlm:
        """기본 모델 설정"""
        is_dev = os.getenv("DEVELOPMENT", "false").lower() == "true"
        
        if is_dev:
            return LiteLlm(
                model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
                api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
            )
        else:
            return LiteLlm(
                model=f"openai/{os.getenv('LLM_DEFAULT_MODEL', 'GLM4.7')}",
                api_base=os.getenv("LLM_BASE_URL", "http://llm-gw.company.com:8000/v1"),
                api_key=os.getenv("LLM_API_KEY", "")
            )
    
    def create_agent(self, chatbot_def: Dict[str, Any]) -> Agent:
        """
        JSON 챗봇 정의를 ADK Agent로 변환
        
        Args:
            chatbot_def: 챗봇 JSON 정의
            
        Returns:
            ADK Agent 인스턴스
        """
        chatbot_id = chatbot_def["id"]
        
        # 캐시 확인
        if chatbot_id in self._agent_cache:
            return self._agent_cache[chatbot_id]
        
        logger.info(f"[SubAgentFactory] Creating agent for {chatbot_id}")
        
        # 하위 챗봇 재귀적 생성
        sub_agents = []
        for sub_def in chatbot_def.get("sub_chatbots", []):
            # 하위 챗봇 정의 조회 (간략화된 버전 - 실제로는 ChatbotManager 사용)
            sub_chatbot = self._get_chatbot_def(sub_def["id"])
            if sub_chatbot:
                sub_agent = self.create_agent(sub_chatbot)
                sub_agents.append(sub_agent)
        
        # 시스템 프롬프트 구성
        system_prompt = self._build_system_prompt(chatbot_def)
        
        # 도구 설정 (하위 챗봇이 있을 경우 위임 도구 추가)
        tools = []
        if sub_agents:
            # LLM에게 위임 결정을 맡기고, 실제 위임은 sub_agents로 처리
            pass  # tools는 sub_agents가 있으면 자동으로 delegate
        
        # Agent 생성
        agent = Agent(
            name=chatbot_id,
            model=self.model,
            instruction=system_prompt,
            description=chatbot_def.get("description", ""),
            sub_agents=sub_agents if sub_agents else None,
        )
        
        # 캐시 저장
        self._agent_cache[chatbot_id] = agent
        
        logger.info(f"[SubAgentFactory] Created agent {chatbot_id} with {len(sub_agents)} sub-agents")
        return agent
    
    def _build_system_prompt(self, chatbot_def: Dict[str, Any]) -> str:
        """시스템 프롬프트 구성"""
        capabilities = chatbot_def.get("capabilities", {})
        policy = chatbot_def.get("policy", {})
        
        base_prompt = capabilities.get("system_prompt", "")
        
        # 위임 관련 프롬프트 추가
        has_subs = bool(chatbot_def.get("sub_chatbots"))
        threshold = policy.get("delegation_threshold", 70)
        
        if has_subs:
            delegation_prompt = f"""

[위임 지침]
당신은 상위 챗봇으로서 다음 하위 전문가들을 관리합니다:
{self._format_sub_chatbots(chatbot_def.get("sub_chatbots", []))}

응답 전략:
1. 질문에 대해 먼저 스스로 답변을 시도하세요
2. 답변 끝에 "CONFIDENCE: XX" 형식으로 신뢰도를 표시하세요 (0-100)
3. 신뢰도가 {threshold}% 미만이거나 전문 상담이 필요하면 하위 전문가에게 위임하세요
4. 하위 위임 시 "DELEGATE_TO: [chatbot_id]"로 명시하세요

상위 Agent로부터 위임받은 경우, 축적된 컨텍스트를 활용하세요.
"""
            base_prompt += delegation_prompt
        else:
            # Leaf 챗봇
            base_prompt += """

[리프 챗봇 지침]
당신은 전문 영역의 최하위 챗봇입니다.
- 검색된 문서를 기반으로 정확하게 답변하세요
- 전문 분야 외 질문에는 "해당 내용은 제 전문 분야가 아닙니다"라고 답변하세요
- 상위 Agent로부터 위임받은 경우, 컨텍스트를 참고하세요
"""
        
        return base_prompt
    
    def _format_sub_chatbots(self, sub_chatbots: List[Dict]) -> str:
        """하위 챗봘 목록 포맷팅"""
        lines = []
        for sub in sub_chatbots:
            sub_id = sub.get("id", "unknown")
            sub_def = self._get_chatbot_def(sub_id)
            if sub_def:
                desc = sub_def.get("description", "")
                keywords = sub_def.get("policy", {}).get("keywords", [])[:5]
                lines.append(f"- {sub_id}: {desc} (키워드: {', '.join(keywords)})")
        return "\n".join(lines) if lines else "(하위 챗봇 정보 없음)"
    
    def _get_chatbot_def(self, chatbot_id: str) -> Optional[Dict[str, Any]]:
        """챗봇 정의 조회 (간략화된 버전)"""
        # TODO: ChatbotManager 연동
        # 임시: chatbots/ 디렉토리에서 JSON 로드
        chatbots_dir = Path(__file__).parent.parent.parent / "chatbots"
        json_file = chatbots_dir / f"{chatbot_id}.json"
        
        if json_file.exists():
            import json
            with open(json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        
        logger.warning(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
        return None
    
    def clear_cache(self):
        """에이전트 캐시 초기화"""
        self._agent_cache.clear()
        logger.info("[SubAgentFactory] Cache cleared")


# 전역 팩토리 인스턴스
_factory: Optional[SubAgentFactory] = None


def get_factory() -> SubAgentFactory:
    """팩토리 싱글톤 반환"""
    global _factory
    if _factory is None:
        _factory = SubAgentFactory()
    return _factory
