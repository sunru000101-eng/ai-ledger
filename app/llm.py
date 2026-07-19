"""模型客户端：OpenAI兼容接口（DeepSeek/Kimi/GLM可切换）。
错误恢复第一层：超时/限流/5xx 自动重试2次，间隔递增。"""
import time

from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    OpenAI, RateLimitError)

from . import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL,
                         timeout=60, max_retries=0)
    return _client


def chat(messages, tools=None):
    kwargs = {"model": config.LLM_MODEL, "messages": messages, "temperature": 0.3}
    if tools:
        kwargs["tools"] = tools
    last = None
    for attempt in range(3):
        try:
            return _get_client().chat.completions.create(**kwargs)
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last = e
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            last = e
        time.sleep(1 + attempt * 2)
    raise last
