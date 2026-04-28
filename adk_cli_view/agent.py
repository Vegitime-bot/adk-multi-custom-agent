"""
ADK CLI Web Console용 Root Agent

이 파일은 adk web 명령어로 실행됩니다:
    adk web adk_cli_view --host 0.0.0.0 --port 8000

ADK Web Console에서 Agent 계층 구조를 시각적으로 확인할 수 있습니다.
"""
import json
import os
import sys

# 프로젝트 루트 추가
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from google.adk.agents import Agent
from adk_agents.sub_agent_factory import SubAgentFactory
from backend.debug_logger import logger

# ── 모든 챗봇 로드 ──────────────────────────────────────────────
factory = SubAgentFactory()
chatbots_dir = os.path.join(_PROJECT_ROOT, 'chatbots')

chatbot_defs = {}
for filename in sorted(os.listdir(chatbots_dir)):
    if filename.endswith('.json'):
        filepath = os.path.join(chatbots_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            chatbot_def = json.load(f)
            chatbot_defs[chatbot_def['id']] = chatbot_def

logger.info(f"[ADKView] Loaded {len(chatbot_defs)} chatbot definitions")

# ── 모든 Agent 생성 (sub_chatbots 제외) ─────────────────────────
agents = {}
for chatbot_id, chatbot_def in chatbot_defs.items():
    try:
        # sub_chatbots를 비워서 tools 없이 순수 Agent만 생성
        def_copy = dict(chatbot_def)
        def_copy['sub_chatbots'] = []
        
        agent = factory.create_agent(def_copy)
        agents[chatbot_id] = agent
        logger.info(f"[ADKView] Created Agent: {chatbot_id}")
    except Exception as e:
        logger.error(f"[ADKView] Failed to create agent {chatbot_id}: {e}")

# ── sub_agents 연결 (계층 구조) ────────────────────────────────
for chatbot_id, chatbot_def in chatbot_defs.items():
    if chatbot_id not in agents:
        continue
    
    parent_agent = agents[chatbot_id]
    for sub_info in chatbot_def.get('sub_chatbots', []):
        sub_id = sub_info['id']
        if sub_id in agents:
            try:
                if parent_agent.sub_agents is None:
                    parent_agent.sub_agents = []
                parent_agent.sub_agents.append(agents[sub_id])
                logger.info(f"[ADKView] Linked {sub_id} as sub_agent of {chatbot_id}")
            except Exception as e:
                logger.error(f"[ADKView] Failed to link {sub_id}: {e}")

# ── Root Agent 설정 ────────────────────────────────────────────
# chatbot_company를 Root로 사용 (없으면 첫 번째)
root_agent = agents.get('chatbot_company')
if root_agent is None and agents:
    root_agent = list(agents.values())[0]

if root_agent:
    logger.info(f"[ADKView] Root agent set: {root_agent.name} (sub_agents: {len(root_agent.sub_agents or [])})")
else:
    logger.error("[ADKView] No root agent available!")

__all__ = ["root_agent"]