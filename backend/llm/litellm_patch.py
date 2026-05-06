"""
LiteLLM patch for internal API compatibility.

Fixes: assistant messages with tool_calls but no content field
cause 422 BadRequestError on some OpenAI-compatible APIs.

Applied automatically on import.
"""
import logging

logger = logging.getLogger(__name__)


def _normalize_openai_messages(messages):
    """
    사내 API 호환성: assistant + tool_calls 메시지에 content=None/누락 시 빈 문자열 보정.

    OpenAI 공식 스펙상 content는 optional 이지만, 일부 사내 API 구현에서는
    assistant 메시지의 content 필드를 required 로 선언해 422를 반환함.
    """
    fixed = []
    for m in messages:
        m = dict(m)
        if m.get("role") == "assistant":
            # tool_calls 또는 function_call 이 있는데 content 필드 자체가 없으면 추가
            if ("tool_calls" in m or "function_call" in m) and "content" not in m:
                m["content"] = ""
            # content가 None이면 빈 문자열로 변환
            if m.get("content") is None:
                m["content"] = ""
        fixed.append(m)
    return fixed


def _patch_litellm():
    try:
        import litellm
    except ImportError:
        logger.warning("[LiteLLM Patch] litellm not installed, skipping patch")
        return

    _original_acompletion = litellm.acompletion

    async def _wrapped_acompletion(*args, **kwargs):
        if "messages" in kwargs:
            kwargs["messages"] = _normalize_openai_messages(kwargs["messages"])
        return await _original_acompletion(*args, **kwargs)

    litellm.acompletion = _wrapped_acompletion

    _original_completion = litellm.completion

    def _wrapped_completion(*args, **kwargs):
        if "messages" in kwargs:
            kwargs["messages"] = _normalize_openai_messages(kwargs["messages"])
        return _original_completion(*args, **kwargs)

    litellm.completion = _wrapped_completion

    logger.info(
        "[LiteLLM Patch] Applied normalize_openai_messages patch for internal API compatibility"
    )


_patch_litellm()
