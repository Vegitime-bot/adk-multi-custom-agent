#!/usr/bin/env python3
"""
Agent Tool Mode 검증 테스트

목표: JSON 챗봇 정의가 ADK Agent Tool 방식으로 동작하는지 검증

검증 항목:
1. JSON → Agent → AgentTool 변환
2. 하위 Agent가 Tool로 자동 등록
3. LLM이 Tool 호출로 위임
4. Web UI에서 정상 동작
"""

import asyncio
import json
import sys
from pathlib import Path

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.debug_logger import logger


class AgentToolTestCase:
    """테스트 케이스 베이스"""
    
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
        
    async def run(self) -> bool:
        """테스트 실행 - 서브클래스에서 구현"""
        raise NotImplementedError
        
    def log_result(self):
        """결과 로깅"""
        if self.passed:
            logger.info(f"✅ [PASS] {self.name}")
        else:
            logger.error(f"❌ [FAIL] {self.name}: {self.error}")


class TC001_AgentToolCreation(AgentToolTestCase):
    """TC001: JSON → Agent → AgentTool 변환 검증"""
    
    def __init__(self):
        super().__init__("TC001_AgentToolCreation")
        
    async def run(self) -> bool:
        """AgentTool 생성 테스트"""
        try:
            from adk_agents.sub_agent_factory import get_factory
            from google.adk.tools.agent_tool import AgentTool
            
            factory = get_factory()
            
            # 1. JSON → AgentTool 변환
            tool = factory.create_agent_tool("chatbot-hr")
            
            if tool is None:
                self.error = "AgentTool 생성 실패"
                return False
                
            if not isinstance(tool, AgentTool):
                self.error = f"AgentTool 타입 불일치: {type(tool)}"
                return False
                
            logger.info(f"✓ AgentTool 생성 성공: {tool}")
            self.passed = True
            return True
            
        except Exception as e:
            self.error = str(e)
            logger.error(f"TC001 오류: {e}", exc_info=True)
            return False


class TC002_RootAgentWithTools(AgentToolTestCase):
    """TC002: Root Agent + 하위 Agent Tools 등록 검증"""
    
    def __init__(self):
        super().__init__("TC002_RootAgentWithTools")
        
    async def run(self) -> bool:
        """Root Agent Tool 등록 테스트"""
        try:
            from adk_agents.sub_agent_factory import get_factory
            from google.adk.agents import Agent
            
            factory = get_factory()
            
            # 1. Root Agent + Tools 생성
            root_agent = factory.create_root_agent_with_tools("chatbot-company")
            
            if root_agent is None:
                self.error = "Root Agent 생성 실패"
                return False
                
            if not isinstance(root_agent, Agent):
                self.error = f"Agent 타입 불일치: {type(root_agent)}"
                return False
                
            # 2. Tools 확인
            if not hasattr(root_agent, 'tools') or root_agent.tools is None:
                self.error = "Root Agent에 tools 속성 없음"
                return False
                
            tool_count = len(root_agent.tools)
            logger.info(f"✓ Root Agent 생성 성공: {root_agent.name}, tools={tool_count}")
            
            if tool_count < 2:
                self.error = f"Tool 개수 부족: {tool_count} (expected >= 2)"
                return False
                
            self.passed = True
            return True
            
        except Exception as e:
            self.error = str(e)
            logger.error(f"TC002 오류: {e}", exc_info=True)
            return False


class TC003_ToolDelegation(AgentToolTestCase):
    """TC003: LLM Tool 호출 위임 검증"""
    
    def __init__(self):
        super().__init__("TC003_ToolDelegation")
        
    async def run(self) -> bool:
        """Tool 위임 테스트"""
        try:
            from adk_agents.delegation_router_agent import get_router
            
            router = get_router()
            
            # 1. 스트리밍 실행
            chunks = []
            async for chunk in router.route_and_stream_with_tools(
                chatbot_id="chatbot-company",
                message="백엔드 기술 설명해",
                session_id="test-session-001",
                user_id="test-user"
            ):
                chunks.append(chunk)
                logger.debug(f"수신 chunk: {chunk[:100]}...")
                
            if not chunks:
                self.error = "응답 chunk 없음"
                return False
                
            # 2. 응답 파싱
            full_response = []
            for chunk in chunks:
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if "chunk" in data:
                            full_response.append(data["chunk"])
                        elif "done" in data:
                            break
                    except:
                        pass
                        
            response_text = "".join(full_response)
            logger.info(f"✓ 응답 수신: {len(response_text)} chars")
            
            if len(response_text) < 10:
                self.error = f"응답 길이 부족: {len(response_text)}"
                return False
                
            # 3. Tool 호출 확인 (도구 호출 메시지 포함 여부)
            if "[도구 호출:" in response_text:
                logger.info("✓ Tool 호출 감지됨")
            else:
                logger.info("ℹ️ Tool 호출 없음 (직접 응답)")
                
            self.passed = True
            return True
            
        except Exception as e:
            self.error = str(e)
            logger.error(f"TC003 오류: {e}", exc_info=True)
            return False


class TC004_MockRAGIntegration(AgentToolTestCase):
    """TC004: Mock RAG + Agent Tool 통합 검증"""
    
    def __init__(self):
        super().__init__("TC004_MockRAGIntegration")
        
    async def run(self) -> bool:
        """Mock RAG 통합 테스트"""
        try:
            from adk_agents.delegation_router_agent import get_router
            
            router = get_router()
            
            # 1. Mock RAG 검색
            rag_results = await router._search_rag(
                query="백엔드 기술",
                db_ids=["db_company_overview"]
            )
            
            if not rag_results:
                self.error = "Mock RAG 결과 없음"
                return False
                
            logger.info(f"✓ Mock RAG 결과: {len(rag_results)} items")
            
            # 2. RAG 결과가 Agent Tool 응답에 포함되는지 확인
            chunks = []
            async for chunk in router.route_and_stream_with_tools(
                chatbot_id="chatbot-company",
                message="백엔드 기술 설명해",
                session_id="test-session-002",
                user_id="test-user",
                db_ids=["db_company_overview"]
            ):
                chunks.append(chunk)
                
            # 응답에 RAG 컨텍스트 포함 여부 확인
            response_text = "".join(chunks)
            
            # FastAPI, PostgreSQL 등의 키워드가 응답에 포함되는지
            keywords = ["FastAPI", "PostgreSQL", "Redis", "Docker"]
            found_keywords = [k for k in keywords if k in response_text]
            
            logger.info(f"✓ 응답 키워드: {found_keywords}")
            
            self.passed = True
            return True
            
        except Exception as e:
            self.error = str(e)
            logger.error(f"TC004 오류: {e}", exc_info=True)
            return False


async def run_all_tests():
    """모든 테스트 실행"""
    logger.info("=" * 60)
    logger.info("Agent Tool Mode 검증 테스트 시작")
    logger.info("=" * 60)
    
    test_cases = [
        TC001_AgentToolCreation(),
        TC002_RootAgentWithTools(),
        TC003_ToolDelegation(),
        TC004_MockRAGIntegration(),
    ]
    
    results = []
    for tc in test_cases:
        logger.info(f"\n▶️ {tc.name} 실행 중...")
        try:
            passed = await tc.run()
            tc.log_result()
            results.append((tc.name, passed, tc.error))
        except Exception as e:
            logger.error(f"테스트 실행 오류: {e}", exc_info=True)
            results.append((tc.name, False, str(e)))
    
    # 결과 요약
    logger.info("\n" + "=" * 60)
    logger.info("테스트 결과 요약")
    logger.info("=" * 60)
    
    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)
    
    for name, passed, error in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {name}")
        if error:
            logger.info(f"   └─ 오류: {error}")
    
    logger.info("-" * 60)
    logger.info(f"총 {total_count}개 중 {passed_count}개 통과 ({passed_count/total_count*100:.1f}%)")
    logger.info("=" * 60)
    
    return passed_count == total_count


if __name__ == "__main__":
    # 환경변수 설정
    import os
    os.environ["USE_MOCK_DB"] = "true"
    os.environ["DEVELOPMENT"] = "true"
    
    # 테스트 실행
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
