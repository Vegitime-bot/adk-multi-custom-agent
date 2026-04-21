from __future__ import annotations
"""
llm/client.py - OpenAI 호환 LLM 클라이언트
사내 엔드포인트(base_url)를 사용하며 SSL verify=False를 기본 적용한다.
스트리밍(SSE)과 논스트리밍 모드를 모두 지원한다.
"""
import httpx
from openai import OpenAI
from typing import Generator

from backend.config import settings
from backend.core.models import ChatbotDef, Message


def _build_client(base_url: str | None = None, api_key: str | None = None) -> OpenAI:
    """SSL verify=False httpx 클라이언트를 탑재한 OpenAI 클라이언트를 생성한다."""
    http_client = httpx.Client(verify=settings.SSL_VERIFY)
    return OpenAI(
        base_url=base_url or settings.LLM_BASE_URL,
        api_key=api_key or settings.LLM_API_KEY,
        http_client=http_client,
        timeout=settings.LLM_TIMEOUT,
    )


# 모듈 수준 기본 클라이언트 (앱 전체에서 공유)
_default_client: OpenAI | None = None


def get_llm_client() -> OpenAI:
    global _default_client
    if _default_client is None:
        _default_client = _build_client()
    return _default_client


def build_messages(
    system_prompt: str,
    history: list[Message],
    user_message: str,
    context: str,
) -> list[dict]:
    """
    LLM에 전달할 메시지 목록을 구성한다.
    system_prompt에 검색 컨텍스트를 포함한다.
    """
    full_system = system_prompt
    if context and context.strip():
        full_system += f"\n\n## 참고 문서\n{context}"

    messages = [{"role": "system", "content": full_system}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message})
    return messages


def stream_chat(
    chatbot_def: ChatbotDef,
    messages: list[dict],
    client: OpenAI | None = None,
) -> Generator[str, None, None]:
    """
    스트리밍 응답 생성기.
    각 청크의 텍스트 델타를 yield한다.
    """
    llm = client or get_llm_client()
    response = llm.chat.completions.create(
        model=chatbot_def.llm.model,
        messages=messages,
        temperature=chatbot_def.llm.temperature,
        max_tokens=chatbot_def.llm.max_tokens,
        stream=True,
    )
    for chunk in response:
        # choices가 비어있는 경우 처리 (사내 LLM 특이 케이스)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def chat_once(
    chatbot_def: ChatbotDef,
    messages: list[dict],
    client: OpenAI | None = None,
) -> str:
    """논스트리밍 응답 생성. 전체 응답 텍스트를 반환한다."""
    llm = client or get_llm_client()
    response = llm.chat.completions.create(
        model=chatbot_def.llm.model,
        messages=messages,
        temperature=chatbot_def.llm.temperature,
        max_tokens=chatbot_def.llm.max_tokens,
        stream=False,
    )
    return response.choices[0].message.content or ""
