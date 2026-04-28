"""
SubAgentFactory - JSON 정의를 ADK Agent로 변환하는 팩토리
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.debug_logger import logger

# ADK import
try:
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.tools.agent_tool import AgentTool
    ADK_AVAILABLE = True
except ImportError as e:
    ADK_AVAILABLE = False
    logger.error(f"[SubAgentFactory] ADK not available: {e}")
    Agent = None
    LiteLlm = None
    AgentTool = None

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
        """기본 모델 설정 - config.py 사용"""
        from backend.config import settings
        
        is_dev = os.getenv("DEVELOPMENT", "false").lower() == "true"
        
        if is_dev:
            # 개발환경: Ollama (config.py 또는 환경변수)
            return LiteLlm(
                model=f"openai/{os.getenv('OLLAMA_MODEL', 'kimi-k2.5:cloud')}",
                api_base=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.getenv("OLLAMA_API_KEY", "dummy-key")
            )
        else:
            # 사내 서버: config.py의 LLM 설정 사용
            return LiteLlm(
                model=f"openai/{settings.LLM_DEFAULT_MODEL}",
                api_base=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY
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
        # ADK Agent 이름은 유효한 식별자여야 함 (하이픈 -> 언더스코어)
        agent_name = chatbot_id.replace("-", "_")
        
        # ADK Agent 이름은 유효한 식별자여야 함 (하이픈 -> 언더스코어)
        agent_name = chatbot_id.replace("-", "_")
        
        # 캐시 확인
        if chatbot_id in self._agent_cache:
            return self._agent_cache[chatbot_id]
        
        logger.info(f"[SubAgentFactory] Creating agent for {chatbot_id} (name: {agent_name})")
        
        # 시스템 프롬프트 구성
        system_prompt = self._build_system_prompt(chatbot_def)
        
        # Agent 생성 (sub_agents 없이 - 위임은 DelegationRouter에서 처리)
        agent = Agent(
            name=agent_name,
            model=self.model,
            instruction=system_prompt,
            description=chatbot_def.get("description", ""),
        )
        
        # 캐시 저장 (원래 chatbot_id로)
        self._agent_cache[chatbot_id] = agent
        
        logger.info(f"[SubAgentFactory] Created agent {chatbot_id}")
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

[출처 표시 규칙 - 반드시 준수]
답변 마지막에 반드시 다음 형식으로 출처를 표시하세요:

---
📚 **출처**: 
- [RAG] 검색된 문서 기반 답변 (검색 결과 사용 시)
- [LLM] AI 생성 답변 (일반 지식/추론 기반 시)
- [RAG+LLM] 문서 기반 + AI 보충 설명 (혼합 시)

예시:
---
📚 **출처**: [RAG] 기술스택 문서 (db_tech_stack), 개발환경 가이드 (db_dev_guide)
---
📚 **출처**: [LLM] 일반 기술 지식 기반 생성
---
📚 **출처**: [RAG+LLM] 기술스택 문서 + AI 보충 설명

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

[출처 표시 규칙 - 반드시 준수]
답변 마지막에 반드시 다음 형식으로 출처를 표시하세요:

---
📚 **출처**: 
- [RAG] 검색된 문서 기반 답변 (검색 결과 사용 시)
- [LLM] AI 생성 답변 (일반 지식/추론 기반 시)
- [RAG+LLM] 문서 기반 + AI 보충 설명 (혼합 시)

예시:
---
📚 **출처**: [RAG] 기술스택 문서 (db_tech_stack), 개발환경 가이드 (db_dev_guide)
---
📚 **출처**: [LLM] 일반 기술 지식 기반 생성
---
📚 **출처**: [RAG+LLM] 기술스택 문서 + AI 보충 설명
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
        chatbots_dir = PROJECT_ROOT / "chatbots"
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
    
    def create_agent_tool(self, chatbot_id: str) -> Optional[Any]:
        """
        JSON → Agent → AgentTool 변환
        
        Args:
            chatbot_id: 챗봇 ID
            
        Returns:
            AgentTool 인스턴스 또는 None
        """
        if not ADK_AVAILABLE or AgentTool is None:
            logger.error("[SubAgentFactory] ADK or AgentTool not available")
            return None
        
        # JSON 정의 로드
        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            logger.warning(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
            return None
        
        # JSON → Agent 생성
        agent = self.create_agent(chatbot_def)
        if not agent:
            logger.warning(f"[SubAgentFactory] Failed to create agent for {chatbot_id}")
            return None
        
        # Agent → Tool 변환
        try:
            tool = AgentTool(agent=agent)
            logger.info(f"[SubAgentFactory] Created AgentTool for {chatbot_id}")
            return tool
        except Exception as e:
            logger.error(f"[SubAgentFactory] Failed to create AgentTool: {e}")
            return None
    
    def create_root_agent_with_tools(self, chatbot_id: str) -> Optional[Any]:
        """
        Root Agent + 하위 Agent Tools 생성
        
        Args:
            chatbot_id: Root 챗봇 ID
            
        Returns:
            Agent 인스턴스 (tools에 하위 Agent들이 등록됨) 또는 None
        """
        if not ADK_AVAILABLE:
            logger.error("[SubAgentFactory] ADK not available")
            return None
        
        # 챗봇 정의 로드
        chatbot_def = self._get_chatbot_def(chatbot_id)
        if not chatbot_def:
            logger.error(f"[SubAgentFactory] Chatbot definition not found: {chatbot_id}")
            return None
        
        capabilities = chatbot_def.get("capabilities", {})
        policy = chatbot_def.get("policy", {})
        sub_chatbots = chatbot_def.get("sub_chatbots", [])
        
        # 하위 챗봘을 Tool로 변환
        tools = []
        for sub in sub_chatbots:
            sub_id = sub.get("id")
            if sub_id:
                sub_tool = self.create_agent_tool(sub_id)
                if sub_tool:
                    tools.append(sub_tool)
                    logger.info(f"[SubAgentFactory] Added {sub_id} as tool to {chatbot_id}")
        
        # 시스템 프롬프트 구성 (하위 챗봘 정보 포함)
        system_prompt = capabilities.get("system_prompt", "")
        if sub_chatbots:
            sub_info = self._format_sub_chatbots_for_tools(sub_chatbots)
            system_prompt += f"\n\n[사용 가능한 하위 전문가 도구]\n{sub_info}\n\n"
            system_prompt += "사용자 질문에 따라 적절한 도구를 호출하세요. 도구를 호출하면 자동으로 해당 전문가에게 위임됩니다."
        
        # Root Agent 생성 (tools 포함)
        try:
            # ADK Agent 이름은 유효한 식별자여야 함 (하이픈 -> 언더스코어)
            agent_name = chatbot_id.replace("-", "_")
            
            # tools가 빈 리스트면 None 대신 빈 리스트를 그대로 전달하거나 생략
            agent_kwargs = dict(
                name=agent_name,
                model=self.model,
                description=chatbot_def.get("description", ""),
                instruction=system_prompt,
                output_key=f"{chatbot_id}_response"
            )
            if tools:
                agent_kwargs["tools"] = tools
            
            root_agent = Agent(**agent_kwargs)
            logger.info(f"[SubAgentFactory] Created root agent {agent_name} with {len(tools)} tools")
            return root_agent
        except Exception as e:
            logger.error(f"[SubAgentFactory] Failed to create root agent: {e}")
            return None
    
    def _format_sub_chatbots_for_tools(self, sub_chatbots: List[Dict]) -> str:
        """하위 챗봘 목록을 Tool 설명용으로 포맷팅"""
        lines = []
        for sub in sub_chatbots:
            sub_id = sub.get("id", "unknown")
            sub_def = self._get_chatbot_def(sub_id)
            if sub_def:
                desc = sub_def.get("description", "")
                lines.append(f"- {sub_id}: {desc}")
        return "\n".join(lines) if lines else "(하위 전문가 없음)"


# 전역 팩토리 인스턴스
_factory: Optional[SubAgentFactory] = None


def get_factory() -> SubAgentFactory:
    """팩토리 싱글톤 반환"""
    global _factory
    if _factory is None:
        _factory = SubAgentFactory()
    return _factory
