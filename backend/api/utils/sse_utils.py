"""
backend/api/utils/sse_utils.py - SSE 응답 유틸리티
"""
from __future__ import annotations

import json
from typing import AsyncGenerator


def sse_event(data: str, event: str = "message") -> str:
    """SSE 이벤트 형식으로 데이터 포맷팅"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    """SSE 스트리밍 완료 이벤트"""
    return "event: done\ndata: {}\n\n"


def sse_error(message: str) -> str:
    """SSE 오류 이벤트"""
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"


async def sse_event_generator(
    message: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    기본적인 SSE 이벤트 생성기
    세션 ID 전송 후 메시지 스트리밍
    """
    yield sse_event(json.dumps({"session_id": session_id}), event="session")
    yield sse_event(message)
    yield sse_done()