"""backend/api/chat.py - ADK 기반 채팅 API"""
import time
import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.api.utils import chat_utils as cu
from backend.api.middleware import auth_middleware as auth
from backend.api.chat_service_adk import get_adk_chat_service
from backend.core.models import ExecutionRole, Message
from backend.debug_logger import logger
from config import settings

# ChatServiceV2 import (JSON 기반 계층 구조)
USE_V2 = os.getenv("USE_CHAT_SERVICE_V2", "false").lower() == "true"
if USE_V2:
    try:
        from backend.api.chat_service_v2 import get_chat_service_v2
        logger.info("[ChatAPI] Using ChatServiceV2 (JSON + ADK hierarchy)")
    except ImportError as e:
        USE_V2 = False
        logger.warning(f"[ChatAPI] ChatServiceV2 not available: {e}")

router = APIRouter(prefix="/api", tags=["chat"])
SR = StreamingResponse


class ChatR(BaseModel):
    chatbot_id: str
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = None
    multi_sub_execution: Optional[bool] = None


class SessionR(BaseModel):
    chatbot_id: str
    session_id: Optional[str] = None
    mode: Optional[str] = None
    active_level: int = 1


class ToolR(BaseModel):
    message: str
    context: Optional[dict] = None


class AgentR(BaseModel):
    message: str
    session_id: str


def _d(r):
    """의존성 객체 반환"""
    return (
        cu.get_chatbot_manager(r),
        cu.get_session_manager(r),
        cu.get_memory_manager(r),
        cu.get_ingestion_client(r)
    )


def _cd(c):
    """챗봇 정의를 클라이언트 응답 형식으로 변환"""
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "default_mode": c.role.value,
        "type": "parent" if c.sub_chatbots else "child" if c.parent_id else "standalone",
        "sub_chatbots": [{"id": s.id} for s in c.sub_chatbots] if c.sub_chatbots else [],
        "parent_id": c.parent_id
    }


def _chk(ps, cid, m):
    """권한 체크"""
    if not (auth.check_chatbot_access(ps, cid) and auth.check_mode_permission(ps, cid, m)):
        raise HTTPException(403)


@router.get("/chatbots")
def list_chatbots(r: Request):
    """활성 챗봇 목록 반환"""
    return [_cd(c) for c in cu.get_chatbot_manager(r).list_active()]


@router.post("/sessions")
def create_session(b: SessionR, r: Request):
    """새 세션 생성"""
    u = auth.get_current_user(r)
    cbm, sm, _, _ = _d(r)
    cb = cbm.get_active(b.chatbot_id)
    if not cb:
        raise HTTPException(404)
    
    return sm.create_session(
        b.chatbot_id,
        u["knox_id"],
        b.session_id,
        {b.chatbot_id: (b.mode or cb.role.value)} if (b.mode or cb.role.value) else None,
        b.active_level
    ).to_dict()


@router.post("/chat")
async def chat(b: ChatR, r: Request):
    """
    ADK 기반 채팅 엔드포인트
    
    ChatServiceV2 사용 시: JSON 기반 계층 구조 + ADK sub_agents
    USE_CHAT_SERVICE_V2=true 환경변수로 활성화
    """
    u = auth.get_current_user(r)
    cbm, sm, mm, ic = _d(r)
    
    cb = cbm.get_active(b.chatbot_id)
    if not cb:
        raise HTTPException(404)
    
    ss = sm.get_or_create(b.chatbot_id, u["knox_id"], b.session_id)
    md = cu.resolve_execution_mode(cb, ss, b.mode)
    _chk(auth.get_user_permissions(u), b.chatbot_id, md.value)
    
    # ChatServiceV2 사용 여부 (런타임 체크)
    use_v2 = os.getenv("USE_CHAT_SERVICE_V2", "false").lower() == "true"
    if use_v2:
        logger.info(f"[ChatAPI] Using V2 for {b.chatbot_id}")
        return await _chat_v2(b, r, u, cbm, sm, mm)
    
    # 기존 V1 방식
    sv = get_adk_chat_service()
    
    async def generate():
        async for event in sv.stream_chat_response(
            chatbot_id=b.chatbot_id,
            message=b.message,
            session_id=ss.session_id,
            user=u,
            system_prompt=cb.system_prompt if hasattr(cb, 'system_prompt') else ""
        ):
            yield event
    
    return SR(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/tools/{cid}")
async def tool(cid: str, b: ToolR, r: Request):
    """Tool 모드 엔드포인트"""
    u = auth.get_current_user(r)
    sv = get_adk_chat_service()
    cb = cu.get_chatbot_manager(r).get_active(cid)
    
    if not cb:
        raise HTTPException(404)
    
    _chk(auth.get_user_permissions(u), cid, "tool")
    
    async def generate():
        async for event in sv.stream_chat_response(
            chatbot_id=cid,
            message=b.message,
            session_id=f"tool-{cid}-{int(time.time() * 1000)}",
            user=u,
            system_prompt=""
        ):
            yield event
    
    return SR(generate(), media_type="text/event-stream")


@router.post("/agents/{cid}")
async def agent(cid: str, b: AgentR, r: Request):
    """Agent 모드 엔드포인트"""
    u = auth.get_current_user(r)
    cbm, sm, mm, ic = _d(r)
    sv = get_adk_chat_service()
    cb = cbm.get_active(cid)
    
    if not cb:
        raise HTTPException(404)
    
    _chk(auth.get_user_permissions(u), cid, "agent")
    ss = sm.get_or_create(cid, u["knox_id"], b.session_id)
    
    async def generate():
        async for event in sv.stream_chat_response(
            chatbot_id=cid,
            message=b.message,
            session_id=ss.session_id,
            user=u,
            system_prompt=cb.system_prompt if hasattr(cb, 'system_prompt') else ""
        ):
            yield event
    
    return SR(generate(), media_type="text/event-stream")


@router.get("/sessions/{sid}/history")
def history(sid: str, chatbot_id: Optional[str] = None, r: Request = None):
    """세션 히스토리 조회 - memory first, postgresql fallback, md file reference support"""
    if r:
        auth.get_current_user(r)

    # memory 조회, (chatbot_id 있을때만)
    messages = []
    if chatbot_id:
        mm = cu.get_memory_manager(r)
        messages = mm.get_history(chatbot_id, sid)

    # Memory에 없으면 PostgreSQL에서 fallback 조회
    if not messages:
        from backend.conversation.repository import get_conversation_repository
        repo = get_conversation_repository()
        logs = repo.get_by_session(sid, limit=100)

        for log in logs:
            user_msg = log.user_message
            assistant_msg = log.assistant_response

            # assistant_response가 MD 파일 경로인지 확인 (.md 확장자 + 실제 존재 여부)
            if isinstance(assistant_msg, str) and assistant_msg.endswith(".md"):
                md_path = Path(assistant_msg)
                # path traversal 방지: 설정된 base dir 하위만 허용
                base_dir = settings.CHAT_HISTORY_DIR.resolve()
                try:
                    md_path_resolved = md_path.resolve()
                    if str(md_path_resolved).startswith(str(base_dir)) and md_path.exists():
                        md_messages = _parse_md_to_messages(md_path)
                        messages.extend(md_messages)
                        continue
                    else:
                        logger.warning(f"[history] MD path outside base_dir or not found: {md_path}")
                except (OSError, RuntimeError) as e:
                    logger.error(f"[history] MD path resolution failed: {e}")
                    # fallback: DB 값 그대로 사용

            # 일반적인 텍스트 응답 (기존 동작)
            messages.append(Message(role="user", content=user_msg))
            messages.append(Message(role="assistant", content=assistant_msg))

    return {"history": [m.to_dict() for m in messages]}


def _parse_md_to_messages(md_path: Path) -> list[Message]:
    """MD 파일을 User/Assistant 블록으로 파싱하여 Message 리스트 반환"""
    messages = []
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"[_parse_md_to_messages] Read failed: {md_path}, error: {e}")
        return messages

    # --- 구분자로 블록 분리 ---
    # 패턴: \n---\n (SSE 방식: ---는 블록 시작/종료)
    blocks = re.split(r'\n---+\n', content)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # User / Assistant 라인 파싱
        user_match = re.search(r'\*\*User\*\*\s*:\s*(.+?)(?=\n\*\*Assistant|$)', block, re.DOTALL)
        assistant_match = re.search(r'\*\*Assistant\*\*\s*:\s*(.+)', block, re.DOTALL)

        if user_match:
            user_content = user_match.group(1).strip()
            if user_content:
                messages.append(Message(role="user", content=user_content))

        if assistant_match:
            assistant_content = assistant_match.group(1).strip()
            if assistant_content:
                messages.append(Message(role="assistant", content=assistant_content))

    return messages


@router.get("/sessions")
def list_sessions(r: Request):
    """사용자 세션 목록 조회"""
    u = auth.get_current_user(r)
    _, sm, _, _ = _d(r)
    ss = sm.list_sessions(user_knox_id=u["knox_id"])  # ✅ 사용자별 필터링
    return {
        "sessions": [
            {"session_id": s.get("session_id"), "chatbot_id": s.get("chatbot_id"), "last_accessed": s.get("last_accessed")}
            for s in ss
        ]
    }


@router.delete("/sessions/{sid}")
def close_session(sid: str, r: Request):
    """세션 종료 — 메모리 + 세션 객체 모두 삭제"""
    auth.get_current_user(r)
    sm, mm = _d(r)[1], _d(r)[2]
    mm.clear_all_for_session(sid)
    sm.close_session(sid)
    return {"message": f"세션 {sid} 종료", "session_id": sid}


# V2 Helper Functions
async def _chat_v2(b: ChatR, r: Request, u, cbm, sm, mm):
    """ChatServiceV2 (JSON 기반 계층 구조 + ADK sub_agents)"""
    from backend.conversation.repository import get_conversation_repository
    
    logger.info(f"[_chat_v2] Starting for {b.chatbot_id}")
    
    try:
        service = get_chat_service_v2(
            chatbot_manager=cbm,
            memory_manager=mm,
            conversation_repo=get_conversation_repository()
        )
        logger.info(f"[_chat_v2] Got service, calling chat_stream")
        
        # SessionManager가 만든 세션 ID 사용 (b.session_id 무시)
        ss = sm.get_or_create(b.chatbot_id, u["knox_id"], b.session_id)
        session_id = ss.session_id
        logger.info(f"[_chat_v2] Using session_id: {session_id}")
        
        # 스트리밍 응답
        stream = service.chat_stream(
            chatbot_id=b.chatbot_id,
            message=b.message,
            session_id=session_id,
            user_id=u["knox_id"],
            mode=b.mode
        )
        logger.info(f"[_chat_v2] Created stream, returning StreamingResponse")
        
        return SR(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
        
    except Exception as e:
        logger.error(f"[ChatV2] Error: {e}", exc_info=True)
        raise HTTPException(500, f"Chat service error: {str(e)}")
