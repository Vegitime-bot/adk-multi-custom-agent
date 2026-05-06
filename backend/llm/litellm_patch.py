"""
LiteLLM patch for internal API compatibility.

Fixes:
1. assistant messages with tool_calls but no content field cause 422
2. Rate limit errors cause immediate failure (adds exponential backoff retry)

Applied automatically on import.
"""
import logging
import asyncio

logger = logging.getLogger(__name__)


def _normalize_openai_messages(messages):
    """
    사내 API 호환성: assistant + tool_calls 메시지에 content=None/누락 시 빈 문자열 보정.
    """
    fixed = []
    for m in messages:
        m = dict(m)
        if m.get("role") == "assistant":
            if ("tool_calls" in m or "function_call" in m) and "content" not in m:
                m["content"] = ""
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

        max_retries = kwargs.pop("_patch_max_retries", 3)
        base_delay = kwargs.pop("_patch_base_delay", 1.0)

        for attempt in range(max_retries + 1):
            try:
                return await _original_acompletion(*args, **kwargs)
            except litellm.RateLimitError as e:
                if attempt == max_retries:
                    logger.error(f"[LiteLLM Patch] RateLimitError after {max_retries} retries: {e}")
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(f"[LiteLLM Patch] RateLimitError, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            except Exception:
                raise

    litellm.acompletion = _wrapped_acompletion

    _original_completion = litellm.completion

    def _wrapped_completion(*args, **kwargs):
        if "messages" in kwargs:
            kwargs["messages"] = _normalize_openai_messages(kwargs["messages"])
        return _original_completion(*args, **kwargs)

    litellm.completion = _wrapped_completion

    logger.info(
        "[LiteLLM Patch] Applied normalize_openai_messages + RateLimit retry patch for internal API compatibility"
    )


_patch_litellm()
