from __future__ import annotations
"""
api/chat.py - 채팅 API + SSE 스트리밍 (Executor 기반 리팩토링)
요청 실행 라이프사이클:
1. 챗봇 정의 조회
2. 사용자 인증 + 권한 검사
3. 세션 확인/생성
4. ExecutionContext 생성
5. Mode에 맞는 Executor 선택 (Tool/Agent)
6. 검색 + LLM 스트리밍
"""
import json
import time
import traceback
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.auth.mock_auth import get_current_user
from backend.config import settings
from backend.core.models import ExecutionRole
from backend.permissions.repository import (
    PermissionRepository,
    get_permission_repository,
)
from backend.debug_logger import logger
from backend.executors import ToolExecutor, AgentExecutor, HierarchicalAgentExecutor
from backend.managers.chatbot_manager import ChatbotManager
from backend.managers.memory_manager import MemoryManager
from backend.managers.session_manager import SessionManager
from backend.retrieval.ingestion_client import IngestionClient
from backend.conversation.repository import (
    ConversationLog,
    ConversationRepository,
    MockConversationRepository,
)

router = APIRouter(prefix="/api", tags=["chat"])


# ── 요청 스키마 ────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    chatbot_id: str
    message: str
    session_id: str | None = None
    mode: str | None = None  # "tool" | "agent" | None (None이면 default_mode 사용)
    role_override: dict[str, str] | None = None  # 하위호환
    active_level: int = 1
    multi_sub_execution: bool | None = None  # 사용자 선택값 (None이면 챗봇 기본값 사용)


class SessionCreateRequest(BaseModel):
    chatbot_id: str
    session_id: str | None = None
    mode: str | None = None
    role_override: dict[str, str] | None = None
    active_level: int = 1


# ── 의존성 ─────────────────────────────────────────────────────────
def get_chatbot_manager(request: Request) -> ChatbotManager:
    return request.app.state.chatbot_manager

def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager

def get_memory_manager(request: Request) -> MemoryManager:
    return request.app.state.memory_manager

def get_ingestion_client(request: Request) -> IngestionClient:
    return request.app.state.ingestion_client


# ═══════════════════════════════════════════════════════════════════
# Phase 4: 권한 모듈 (Mode 기반 접근 제어)
# ═══════════════════════════════════════════════════════════════════

# 모의 사용자 권한 데이터 (실제 환경에서는 PostgreSQL에서 조회)
MOCK_USER_PERMISSIONS = {
    "user-001": {  # 일반 사용자
        "chatbot-a": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool"]},  # Tool만
        "chatbot-c": {"access": True, "allowed_modes": ["tool", "agent"]},
        # RTL 하위 챗봇 권한
        "chatbot-rtl-verilog": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-rtl-synthesis": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-company": {"access": True, "allowed_modes": ["tool", "agent"]},
        # 상위/하위 챗봇 권한
        "chatbot-hr": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool", "agent"]},
    },
    "user-002": {  # 관리자
        "chatbot-a": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-c": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-d": {"access": True, "allowed_modes": ["tool", "agent"]},
        # 상위/하위 챗봇 권한 (전체 접근)
        "chatbot-hr": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool", "agent"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool", "agent"]},
    },
    "system": {  # 시스템 계정 (내부 호출용)
        "chatbot-a": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-b": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-c": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-d": {"access": True, "allowed_modes": ["tool"]},
        # 상위/하위 챗봇 권한
        "chatbot-hr": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-hr-policy": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-hr-benefit": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-backend": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-frontend": {"access": True, "allowed_modes": ["tool"]},
        "chatbot-tech-devops": {"access": True, "allowed_modes": ["tool"]},
    },
}


def get_user_permissions(user: dict) -> dict:
    """사용자의 챗봇별 권한 조회 (DB 연동)"""
    knox_id = user.get("knox_id", "unknown")
    
    # PermissionRepository로 실제 DB 조회
    try:
        repo = get_permission_repository(use_mock=settings.USE_MOCK_DB)
        perms = repo.get_user_permissions(knox_id)
        
        # {chatbot_id: {"access": bool, "allowed_modes": [...]}} 형태로 변환
        result = {}
        for p in perms:
            chatbot_id = p.get("chatbot_id")
            can_access = p.get("can_access", False)
            if chatbot_id:
                result[chatbot_id] = {
                    "access": can_access,
                    "allowed_modes": ["tool", "agent"]  # DB에 모드 정보 없으면 기본값
                }
        
        if result:
            return result
    except Exception as e:
        logger.warning(f"[get_user_permissions] DB 조회 실패: {e}")
    
    # DB 조회 실패 또는 권한 없으면 Mock 데이터 사용 (임시)
    return MOCK_USER_PERMISSIONS.get("user-001", {})


def load_restricted_chatbots() -> set[str]:
    """파일에서 제한된 챗봇 목록 로드"""
    import json
    from pathlib import Path
    file_path = Path(__file__).parent.parent.parent / "data" / "restricted_chatbots.json"
    if file_path.exists():
        data = json.loads(file_path.read_text())
        return set(data.get("chatbots", []))
    return set()


# 제한된 챗봇 목록 (이 챗봇들만 권한 체크)
RESTRICTED_CHATBOTS: set[str] = load_restricted_chatbots()


def check_chatbot_access(permissions: dict, chatbot_id: str) -> bool:
    """챗봇 접근 권한 확인 - 기본 허용, 특정 챗봇만 체크
    
    정책:
    1. RESTRICTED_CHATBOTS가 비어있으면 → 모든 챗봇 허용 (기본 오픈)
    2. RESTRICTED_CHATBOTS에 있는 챗봇만 → DB 권한 테이블에서 명시적 허가 확인
    3. 그 외 챗봇 → 모두 허용
    """
    # Test chatbots always allowed
    if chatbot_id.startswith("test-"):
        return True
    
    # Mock mode: allow all chatbots by default (for development)
    if settings.USE_MOCK_AUTH:
        return True
    
    # ★ 핵심 수정: 제한된 챗봇 목록이 비어있으면 모든 챗봇 허용
    if not RESTRICTED_CHATBOTS:
        logger.debug(f"[check_chatbot_access] RESTRICTED_CHATBOTS 비어있음 → {chatbot_id} 허용")
        return True
    
    # 제한된 챗봇이 아니면 기본적으로 허용
    if chatbot_id not in RESTRICTED_CHATBOTS:
        logger.debug(f"[check_chatbot_access] {chatbot_id}는 제한 목록에 없음 → 허용")
        return True
    
    # 제한된 챗봇만 권한 체크 (DB의 user_chatbot_access 테이블에서 확인)
    bot_perm = permissions.get(chatbot_id, {})
    can_access = bot_perm.get("access", False)
    logger.info(f"[check_chatbot_access] {chatbot_id}는 제한된 챗봇 → 권한: {can_access}")
    return can_access


def check_mode_permission(permissions: dict, chatbot_id: str, mode: str) -> bool:
    """특정 mode 사용 권한 확인 - 기본 허용, 제한된 챗봇만 체크
    
    정책:
    1. RESTRICTED_CHATBOTS가 비어있으면 → 모든 모드 허용
    2. 제한된 챗봇이 아니면 → 모든 모드 허용
    3. 제한된 챗봇만 → DB의 allowed_modes 조회 후 확인
    """
    # Test chatbots always allowed all modes
    if chatbot_id.startswith("test-"):
        return True
    
    # Mock mode: allow all modes by default (for development)
    if settings.USE_MOCK_AUTH:
        return True
    
    # ★ 핵심 수정: 제한된 챗봇 목록이 비어있으면 모든 모드 허용
    if not RESTRICTED_CHATBOTS:
        logger.debug(f"[check_mode_permission] RESTRICTED_CHATBOTS 비어있음 → {chatbot_id}/{mode} 허용")
        return True
    
    # 제한된 챗봇이 아니면 모든 모드 허용
    if chatbot_id not in RESTRICTED_CHATBOTS:
        logger.debug(f"[check_mode_permission] {chatbot_id}는 제한 목록에 없음 → {mode} 허용")
        return True
    
    # 제한된 챗봇만 모드 권한 체크
    bot_perm = permissions.get(chatbot_id, {})
    if not bot_perm.get("access", False):
        logger.warning(f"[check_mode_permission] {chatbot_id} 접근 권한 없음 → {mode} 차단")
        return False
    
    allowed = bot_perm.get("allowed_modes", [])
    has_permission = mode in allowed
    logger.info(f"[check_mode_permission] {chatbot_id}는 제한된 챗봇 → {mode} 권한: {has_permission} (허용: {allowed})")
    return has_permission


# ── 사용자 DB 스코프 ──
# TODO: 실제 DB에서 사용자-DB 권한 조회하도록 변경
MOCK_USER_DB_SCOPE = {
    "user-001": {"db_001", "db_002", "db_003", "db_004", "db_005"},  # 관리자: 전체
    "user-002": {"db_001"},  # 인사팀: 제한된 권한
    "user-003": {"db_002", "db_003"},  # 기술팀: 일부 권한
    "guest": {"db_001"},  # 게스트: 최소 권한
    "jyd1234": {"db_001", "db_002", "db_003", "db_004", "db_005"},  # mock 기본 사용자
    "yd86.jang": {"db_001", "db_002", "db_003", "db_004", "db_005", "snp"},  # 실제 사용자
}

def get_user_db_scope(user: dict) -> set[str]:
    """
    사용자가 접근 가능한 DB 목록 조회
    - 실제 DB 연동 시 PermissionRepository 확장 필요
    """
    knox_id = user.get("knox_id", "unknown")
    
    if settings.USE_MOCK_AUTH:
        scope = MOCK_USER_DB_SCOPE.get(knox_id, set())
        logger.info(f"[DB Scope] 사용자 {knox_id}의 접근 가능 DB: {scope}")
        return scope
    
    # TODO: 실제 DB에서 사용자-DB 권한 조회
    # repo = get_permission_repository(use_mock=False)
    # return repo.get_user_db_scope(knox_id)
    return set()


# ── SSE 헬퍼 ──────────────────────────────────────────────────────
def sse_event(data: str, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    return "event: done\ndata: {}\n\n"


def sse_error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"


# ── Executor 팩토리 ───────────────────────────────────────────────
def create_executor(
    mode: ExecutionRole,
    chatbot_def,
    ingestion_client: IngestionClient,
    memory_manager: MemoryManager,
    chatbot_manager=None,
):
    """모드에 맞는 Executor 생성
    
    하위 챗봘이 있거나 상위 위임이 필요한 경우 HierarchicalAgentExecutor 사용
    """
    if mode == ExecutionRole.TOOL:
        return ToolExecutor(chatbot_def, ingestion_client)
    
    # Agent 모드: 계층적 위임 지원을 위해 HierarchicalAgentExecutor 사용
    return HierarchicalAgentExecutor(
        chatbot_def=chatbot_def,
        ingestion_client=ingestion_client,
        memory_manager=memory_manager,
        chatbot_manager=chatbot_manager,
        accumulated_context="",
        delegation_depth=0,
    )


# ── 챗봇 목록 ─────────────────────────────────────────────────────
@router.get("/chatbots")
def list_active_chatbots(
    request: Request,
    manager: ChatbotManager = Depends(get_chatbot_manager),
):
    logger.info(f"[API] /api/chatbots 호출됨")
    user = get_current_user(request)
    chatbots = [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "supported_modes": ["tool", "agent"],
            "default_mode": c.role.value,
            "role": c.role.value,
            "type": "parent" if c.sub_chatbots and len(c.sub_chatbots) > 0 else ("child" if c.parent_id else "standalone"),
            "sub_chatbots": [{"id": s.id, "level": s.level} for s in c.sub_chatbots] if c.sub_chatbots else [],
            "parent_id": c.parent_id,
            "policy": c.policy if c.policy else {},
            "keywords": c.keywords if c.keywords else [],
        }
        for c in manager.list_active()
    ]
    logger.info(f"[API] 챗봇 {len(chatbots)}개 반환")
    return chatbots


# ── 세션 생성 ─────────────────────────────────────────────────────
@router.post("/sessions")
def create_session(
    body: SessionCreateRequest,
    request: Request,
    session_mgr: SessionManager = Depends(get_session_manager),
    chatbot_mgr: ChatbotManager = Depends(get_chatbot_manager),
):
    user = get_current_user(request)
    chatbot = chatbot_mgr.get_active(body.chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=404, detail=f"활성 챗봇을 찾을 수 없습니다: {body.chatbot_id}")

    # mode 설정 (하위호환: role_override 지원)
    mode = body.mode
    if not mode and body.role_override:
        mode = body.role_override.get(body.chatbot_id)
    
    # mode가 없으면 챗봇의 default 사용
    if not mode:
        mode = chatbot.role.value

    session = session_mgr.create_session(
        chatbot_id=body.chatbot_id,
        user_knox_id=user["knox_id"],
        session_id=body.session_id,
        role_override={body.chatbot_id: mode} if mode else None,
        active_level=body.active_level,
    )
    return session.to_dict()


# ── 채팅 (SSE 스트리밍) - Executor 기반 ──────────────────────────
@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    chatbot_mgr: ChatbotManager = Depends(get_chatbot_manager),
    session_mgr: SessionManager = Depends(get_session_manager),
    memory_mgr: MemoryManager = Depends(get_memory_manager),
    ingestion_client: IngestionClient = Depends(get_ingestion_client),
):
    start_time = time.time()
    request_id = f"{int(start_time * 1000)}"
    
    logger.info(f"[Chat {request_id}] ========== 새 채팅 요청 ==========")
    logger.info(f"[Chat {request_id}] chatbot_id: {body.chatbot_id}")
    logger.info(f"[Chat {request_id}] message: {body.message[:50]}...")
    logger.info(f"[Chat {request_id}] session_id: {body.session_id}")
    logger.info(f"[Chat {request_id}] mode: {body.mode}")
    logger.info(f"[Chat {request_id}] session_id from request: '{body.session_id}'")  # 추가

    # 1. 챗봇 정의 조회
    chatbot_def = chatbot_mgr.get_active(body.chatbot_id)
    if not chatbot_def:
        raise HTTPException(status_code=404, detail=f"활성 챗봇을 찾을 수 없습니다: {body.chatbot_id}")
    logger.info(f"[Chat {request_id}] 챗봇 조회 성공: {chatbot_def.name}")

    # 2. 세션 확인/생성
    logger.info(f"[Chat {request_id}] Calling get_or_create with session_id={body.session_id}")
    session = session_mgr.get_or_create(
        chatbot_id=body.chatbot_id,
        user_knox_id=get_current_user(request)["knox_id"],
        session_id=body.session_id,
    )
    logger.info(f"[Chat {request_id}] 세션 결과: {session.session_id}")

    # 3. 모드 결정 (요청 > 세션 > 챗봇 default)
    mode_str = body.mode
    if not mode_str and session.role_override.get(body.chatbot_id):
        mode_str = session.role_override[body.chatbot_id].value
    if not mode_str:
        mode_str = chatbot_def.role.value
    
    try:
        mode = ExecutionRole(mode_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"잘못된 mode: {mode_str}")
    
    logger.info(f"[Chat {request_id}] 실행 mode: {mode.value}")

    # 4. DB 스코프 계산
    # 챗봇 접근 권한이 있으면 해당 챗봇의 모든 DB 허용
    requested_db_ids = chatbot_def.retrieval.db_ids
    user = get_current_user(request)
    permissions = get_user_permissions(user)
    
    if check_chatbot_access(permissions, body.chatbot_id):
        authorized_db_ids = list(requested_db_ids)
        logger.info(f"[Chat {request_id}] 챗봇 접근 권한으로 DB 허용: {authorized_db_ids}")
    else:
        # 챗봇 접근 권한 없음
        logger.error(f"[Chat {request_id}] 사용자 {user['knox_id']}의 챗봇 접근 권한 없음: {body.chatbot_id}")
        raise HTTPException(
            status_code=403,
            detail=f"해당 챗봇에 접근할 권한이 없습니다: {body.chatbot_id}"
        )

    # 5. Mode 권한 확인
    if not check_mode_permission(permissions, body.chatbot_id, mode.value):
        logger.error(f"[Chat {request_id}] mode 권한 없음: {mode.value}")
        raise HTTPException(
            status_code=403,
            detail=f"{mode.value} 모드 사용 권한이 없습니다. 허용된 모드: {permissions.get(body.chatbot_id, {}).get('allowed_modes', [])}"
        )

    logger.info(f"[Chat {request_id}] 권한 확인 완료")

    # 6. Executor 생성 (상위 챗봇 체크)
    # 사용자 선택값이 있으면 policy에 반영
    if body.multi_sub_execution is not None:
        chatbot_def.policy['multi_sub_execution'] = body.multi_sub_execution
        logger.info(f"[Chat {request_id}] multi_sub_execution: {body.multi_sub_execution} (사용자 선택)")
    
    executor = create_executor(
        mode, chatbot_def, ingestion_client, memory_mgr, chatbot_mgr
    )
    logger.info(f"[Chat {request_id}] Executor: {executor.__class__.__name__}")

    # Conversation logger
    conv_repo = MockConversationRepository()

    # 6. SSE 스트리밍
    async def event_generator() -> AsyncGenerator[str, None]:
        # 먼저 session_id 전송 (클라이언트 저장용)
        yield sse_event(json.dumps({"session_id": session.session_id}), event="session")
        
        full_response = []
        chunk_count = 0
        llm_start_time = time.time()
        search_results_count = 0
        confidence_score = None
        delegated_to = None
        
        # Executor에서 추가 정보 추출 시도
        if hasattr(executor, '_last_search_results'):
            search_results_count = len(executor._last_search_results)
        if hasattr(executor, '_last_confidence'):
            confidence_score = executor._last_confidence
        if hasattr(executor, '_last_delegated_to'):
            delegated_to = executor._last_delegated_to
        
        try:
            for chunk in executor.execute(body.message, session.session_id):
                chunk_count += 1
                full_response.append(chunk)
                yield sse_event(chunk)
                
                if chunk_count % 100 == 0:
                    elapsed = time.time() - llm_start_time
                    logger.info(f"[Chat {request_id}] 스트리밍 중... {chunk_count} chunks")
                    
        except Exception as e:
            logger.error(f"[Chat {request_id}] 스트리밍 실패: {str(e)}")
            logger.error(f"[Chat {request_id}] {traceback.format_exc()}")
            yield sse_error(f"실행 오류: {str(e)}")
            return

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"[Chat {request_id}] 스트리밍 완료: {chunk_count} chunks, {llm_elapsed:.1f}s")

        yield sse_done()
        
        # 대화 기록 저장
        try:
            from datetime import datetime
            conv_log = ConversationLog(
                id=None,
                session_id=session.session_id,
                knox_id=user["knox_id"],
                chatbot_id=body.chatbot_id,
                user_message=body.message,
                assistant_response="".join(full_response),
                tokens_used=chunk_count * 4,  # Approximate
                latency_ms=int(llm_elapsed * 1000),
                search_results_count=search_results_count,
                confidence_score=confidence_score,
                delegated_to=delegated_to,
                created_at=datetime.now(),
            )
            conv_repo.save(conv_log)
            logger.info(f"[Chat {request_id}] 대화 기록 저장 완료")
        except Exception as e:
            logger.error(f"[Chat {request_id}] 대화 기록 저장 실패: {e}")
        
        total_elapsed = time.time() - start_time
        logger.info(f"[Chat {request_id}] ========== 완료 ({total_elapsed:.1f}s) ==========")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ── 대화 기록 조회 ────────────────────────────────────────────────
@router.get("/sessions/{session_id}/history")
def get_history(
    session_id: str,
    chatbot_id: str,
    request: Request,
    memory_mgr: MemoryManager = Depends(get_memory_manager),
):
    get_current_user(request)
    history = memory_mgr.get_history(chatbot_id=chatbot_id, session_id=session_id)
    return [m.to_dict() for m in history]


# ── 세션 종료 ─────────────────────────────────────────────────────
@router.delete("/sessions/{session_id}")
def close_session(
    session_id: str,
    request: Request,
    session_mgr: SessionManager = Depends(get_session_manager),
    memory_mgr: MemoryManager = Depends(get_memory_manager),
):
    get_current_user(request)
    memory_mgr.clear_all_for_session(session_id)
    session_mgr.close_session(session_id)
    return {"message": f"세션 {session_id} 종료 완료"}


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Tool / Agent 전용 엔드포인트
# ═══════════════════════════════════════════════════════════════════

class ToolRequest(BaseModel):
    """Tool 모드 요청 - 단발성 함수 호출"""
    message: str
    context: dict | None = None  # 추가 컨텍스트 (선택)


class AgentRequest(BaseModel):
    """Agent 모드 요청 - 대화형"""
    message: str
    session_id: str  # Agent는 세션 필수


# ── Tool 전용 엔드포인트 ──────────────────────────────────────────
@router.post("/tools/{chatbot_id}")
async def chat_tool(
    chatbot_id: str,
    body: ToolRequest,
    request: Request,
    chatbot_mgr: ChatbotManager = Depends(get_chatbot_manager),
    ingestion_client: IngestionClient = Depends(get_ingestion_client),
):
    """
    Tool 모드 전용 엔드포인트
    - 단발성 호출 (함수처럼)
    - 메모리 없음
    - 외부 오케스트레이터 연동에 적합
    """
    start_time = time.time()
    request_id = f"{int(start_time * 1000)}"
    
    logger.info(f"[Tool {request_id}] ========== Tool 요청 ==========")
    logger.info(f"[Tool {request_id}] chatbot_id: {chatbot_id}")
    logger.info(f"[Tool {request_id}] message: {body.message[:50]}...")

    # 1. 챗봇 정의 조회
    chatbot_def = chatbot_mgr.get_active(chatbot_id)
    if not chatbot_def:
        raise HTTPException(status_code=404, detail=f"활성 챗봇을 찾을 수 없습니다: {chatbot_id}")
    logger.info(f"[Tool {request_id}] 챗봇: {chatbot_def.name}")

    # 2. 권한 확인 (Phase 4)
    user = get_current_user(request)
    permissions = get_user_permissions(user)
    if not check_chatbot_access(permissions, chatbot_id):
        raise HTTPException(status_code=403, detail=f"해당 챗봇에 접근할 권한이 없습니다: {chatbot_id}")
    if not check_mode_permission(permissions, chatbot_id, "tool"):
        raise HTTPException(status_code=403, detail=f"Tool 모드 사용 권한이 없습니다")
    
    # 3. DB 스코프 계산
    user_db_scope = get_user_db_scope(user)
    requested_db_ids = chatbot_def.retrieval.db_ids
    authorized_db_ids = [
        db_id for db_id in requested_db_ids
        if db_id in user_db_scope
    ]
    
    # DB 접근 권한 체크
    if not authorized_db_ids:
        missing_dbs = set(requested_db_ids) - user_db_scope
        logger.error(f"[Tool {request_id}] 사용자 {user['knox_id']}의 DB 접근 권한 없음: {missing_dbs}")
        raise HTTPException(
            status_code=403,
            detail=f"해당 챗봇에 접근할 수 있는 데이터베이스 권한이 없습니다."
        )
    
    logger.info(f"[Tool {request_id}] 권한 확인 완료")
    logger.info(f"[Tool {request_id}] authorized_db_ids: {authorized_db_ids}")

    # 4. Tool Executor 생성
    executor = ToolExecutor(chatbot_def, ingestion_client)
    logger.info(f"[Tool {request_id}] ToolExecutor 생성")

    # 4. SSE 스트리밍
    async def event_generator() -> AsyncGenerator[str, None]:
        full_response = []
        chunk_count = 0
        
        try:
            for chunk in executor.execute(body.message, session_id=None):
                chunk_count += 1
                full_response.append(chunk)
                yield sse_event(chunk)
                
        except Exception as e:
            logger.error(f"[Tool {request_id}] 오류: {str(e)}")
            yield sse_error(f"실행 오류: {str(e)}")
            return

        yield sse_done()
        logger.info(f"[Tool {request_id}] 완료 ({len(''.join(full_response))}자)")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Agent 전용 엔드포인트 ─────────────────────────────────────────
@router.post("/agents/{chatbot_id}")
async def chat_agent(
    chatbot_id: str,
    body: AgentRequest,
    request: Request,
    chatbot_mgr: ChatbotManager = Depends(get_chatbot_manager),
    session_mgr: SessionManager = Depends(get_session_manager),
    memory_mgr: MemoryManager = Depends(get_memory_manager),
    ingestion_client: IngestionClient = Depends(get_ingestion_client),
):
    """
    Agent 모드 전용 엔드포인트
    - 대화형 (세션 기반)
    - 메모리 유지
    - 사용자와 지속적 대화에 적합
    """
    start_time = time.time()
    request_id = f"{int(start_time * 1000)}"
    
    logger.info(f"[Agent {request_id}] ========== Agent 요청 ==========")
    logger.info(f"[Agent {request_id}] chatbot_id: {chatbot_id}")
    logger.info(f"[Agent {request_id}] session_id: {body.session_id}")

    # 1. 챗봇 정의 조회
    chatbot_def = chatbot_mgr.get_active(chatbot_id)
    if not chatbot_def:
        raise HTTPException(status_code=404, detail=f"활성 챗봇을 찾을 수 없습니다: {chatbot_id}")
    logger.info(f"[Agent {request_id}] 챗봇: {chatbot_def.name}")

    # 2. 권한 확인 (Phase 4)
    user = get_current_user(request)
    permissions = get_user_permissions(user)
    if not check_chatbot_access(permissions, chatbot_id):
        raise HTTPException(status_code=403, detail=f"해당 챗봇에 접근할 권한이 없습니다: {chatbot_id}")
    if not check_mode_permission(permissions, chatbot_id, "agent"):
        raise HTTPException(status_code=403, detail=f"Agent 모드 사용 권한이 없습니다")
    
    # 3. DB 스코프 계산
    user_db_scope = get_user_db_scope(user)
    requested_db_ids = chatbot_def.retrieval.db_ids
    authorized_db_ids = [
        db_id for db_id in requested_db_ids
        if db_id in user_db_scope
    ]
    
    # DB 접근 권한 체크
    if not authorized_db_ids:
        missing_dbs = set(requested_db_ids) - user_db_scope
        logger.error(f"[Agent {request_id}] 사용자 {user['knox_id']}의 DB 접근 권한 없음: {missing_dbs}")
        raise HTTPException(
            status_code=403,
            detail=f"해당 챗봇에 접근할 수 있는 데이터베이스 권한이 없습니다."
        )
    
    logger.info(f"[Agent {request_id}] 권한 확인 완료")
    logger.info(f"[Agent {request_id}] authorized_db_ids: {authorized_db_ids}")

    # 4. 세션 확인/생성
    session = session_mgr.get_or_create(
        chatbot_id=chatbot_id,
        user_knox_id=user["knox_id"],
        session_id=body.session_id,
    )
    logger.info(f"[Agent {request_id}] 세션: {session.session_id}")

    # 4. Agent Executor 생성 (상위 챗봇 체크)
    executor = create_executor(
        ExecutionRole.AGENT, chatbot_def, ingestion_client, memory_mgr, chatbot_mgr
    )
    logger.info(f"[Agent {request_id}] Executor: {executor.__class__.__name__}")

    # 4. SSE 스트리밍
    async def event_generator() -> AsyncGenerator[str, None]:
        # 먼저 session_id 전송 (클라이언트 저장용)
        yield sse_event(json.dumps({"session_id": session.session_id}), event="session")
        
        full_response = []
        chunk_count = 0
        
        try:
            for chunk in executor.execute(body.message, session_id=session.session_id):
                chunk_count += 1
                full_response.append(chunk)
                yield sse_event(chunk)
                
        except Exception as e:
            logger.error(f"[Agent {request_id}] 오류: {str(e)}")
            yield sse_error(f"실행 오류: {str(e)}")
            return

        yield sse_done()
        logger.info(f"[Agent {request_id}] 완료 ({len(''.join(full_response))}자)")

    return StreamingResponse(event_generator(), media_type="text/event-stream")
