#!/usr/bin/env python3
"""
하위 Agent를 별도 프로세스에서 실행하는 스크립트.
완전한 프로세스 격리로 이벤트 루프 충돌을 방지합니다.

사용법:
    python run_subagent.py <chatbot_id> <request_json>
"""
import sys
import json
import asyncio
import os

# 프로젝트 루트 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adk_agents.sub_agent_factory import SubAgentFactory


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python run_subagent.py <chatbot_id> <request>"}))
        sys.exit(1)
    
    chatbot_id = sys.argv[1]
    request = sys.argv[2]
    
    try:
        # Factory 생성 및 Agent 로드
        factory = SubAgentFactory()
        chatbot_def = factory._get_chatbot_def(chatbot_id)
        
        if not chatbot_def:
            print(json.dumps({"error": f"Chatbot not found: {chatbot_id}"}))
            sys.exit(1)
        
        # Agent 생성
        agent = factory.create_agent(chatbot_def)
        if not agent:
            print(json.dumps({"error": f"Failed to create agent for {chatbot_id}"}))
            sys.exit(1)
        
        # Agent 실행
        async def _run():
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
            
            session_service = InMemorySessionService()
            session = await session_service.create_session(
                app_name=chatbot_id,
                user_id="subagent",
                state={}
            )
            
            runner = Runner(
                agent=agent,
                app_name=chatbot_id,
                session_service=session_service
            )
            
            content = types.Content(
                role='user',
                parts=[types.Part(text=request)]
            )
            
            full_response = []
            async for event in runner.run_async(
                user_id="subagent",
                session_id=session.id,
                new_message=content
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            full_response.append(part.text)
            
            return "".join(full_response)
        
        result = asyncio.run(_run())
        print(json.dumps({"result": result, "chatbot_id": chatbot_id}))
        
    except Exception as e:
        import traceback
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
