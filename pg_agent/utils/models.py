import os
import asyncio
import httpx
import logging
from openai import AsyncOpenAI
from volcenginesdkarkruntime import Ark
from openai import OpenAI  # Used for Hunyuan
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from urllib.parse import urlparse


def get_llm(model_name: str):
    """
    Returns an instance of a LangChain-compatible LLM based on the model name.

    Supported:
    - "gpt*" or "o3": ChatOpenAI
    - "claude*": ChatAnthropic

    Raises:
    - ValueError for unsupported model names or missing API keys.
    """
    if model_name.startswith("gpt") or model_name == "o3":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set.")
        return ChatOpenAI(model=model_name, api_key=api_key)

    elif model_name.startswith("claude"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        return ChatAnthropic(model=model_name, api_key=api_key)

    else:
        raise ValueError(f"Unsupported model: {model_name}")


def get_async_llm(model_type: str, model_name: str, api_key: str, max_tokens: int = None, enable_thinking: bool = False):
    """Get an async LLM client instance based on the model type.
    
    Args:
        model_type: The type/provider of the model (e.g. "qwen", "claude", "o3")
        model_name: The specific model name/identifier
        api_key: The API key for the model provider
        max_tokens: Maximum number of tokens to generate
        enable_thinking: Enable thinking mode for models that support it (Alibaba only)
        
    Returns:
        An instance of AsyncLLMClient or its subclasses
        
    Raises:
        ValueError: If the model type is not supported
    """
    common_params = {
        "model": model_name,
        "api_key": api_key,
        "max_tokens": max_tokens
    }
    
    if model_type.startswith("qwen"):
        return AsyncAlibabaClient(
            **common_params,
            enable_thinking=enable_thinking
        )
    elif model_type.startswith("doubao"):
        return AsyncBytedanceClient(**common_params)
    elif model_type.startswith("hunyuan"):
        return AsyncTencentClient(**common_params)
    elif model_type.startswith("o3"):
        return AsyncOpenAIClient(**common_params)
    elif model_type.startswith("claude"):
        return AsyncAnthropicClient(**common_params)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")


# ========= Custom Async LLM Wrappers =========
class AsyncLLMClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        env_key: str,
        base_url: str,
        temperature: float = None,
        max_tokens: int = None,
        timeout: float = 600.0,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)

        self.api_key = api_key or os.getenv(env_key)
        if not self.api_key:
            raise ValueError(f"{env_key} not set.")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(timeout)),
        )

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]
        params = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        params = {k: v for k, v in params.items() if v is not None}
        self.logger.info("🤖 Invoking %s with params: %s", self.model, params)
        response = await self.client.chat.completions.create(
            messages=chat_messages,
            **params
        )
        return response.choices[0].message


class AsyncOpenAIClient(AsyncLLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        temperature: float = None,
        max_tokens: int = None,
        timeout: float = 600.0,
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            env_key="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",

            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )


class AsyncAnthropicClient(AsyncLLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        temperature: float = None,
        max_tokens: int = None,
        timeout: float = 600.0,
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            env_key="ANTHROPIC_API_KEY",
            base_url="https://api.anthropic.com/v1",

            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

class AsyncBytedanceClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None,
        retries: int = 3,
        delay: int = 3
    ):
        self.model = model
        self.client = Ark(api_key=api_key)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.retries = retries
        self.delay = delay
        self.logger = logging.getLogger(__name__)

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]
        for attempt in range(1, self.retries + 1):
            try:
                params = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature
                }
                # Remove None values
                params = {k: v for k, v in params.items() if v is not None}
                
                self.logger.info("🤖 Invoking Bytedance model with params: %s", params)
                
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    messages=chat_messages,
                    **params
                )
                return response.choices[0].message
            except Exception as e:
                error_str = str(e).lower()
                if ("timeout" in error_str or "500" in error_str) and attempt < self.retries:
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Bytedance API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")


class AsyncAlibabaClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None,
        enable_thinking: bool = False,
        thinking_budget: int = 38912,
        retries: int = 3,
        delay: int = 3,
        timeout: float = 600.0
    ):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.retries = retries
        self.delay = delay
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)

        self.is_fireworks = model.startswith("accounts/fireworks/models/")

        if self.is_fireworks:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://api.fireworks.ai/inference/v1",
                http_client=httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
            )
        else:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                http_client=httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
            )

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]

        for attempt in range(1, self.retries + 1):
            try:
                extra_body = None
                if not self.is_fireworks and self.enable_thinking:
                    extra_body = {
                        "enable_thinking": True,
                        "thinking_budget": self.thinking_budget
                    }

                params = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "stream": False
                }
                # Remove None values
                params = {k: v for k, v in params.items() if v is not None}
                
                if extra_body:
                    params["extra_body"] = extra_body
                
                self.logger.info("🤖 Invoking Alibaba model with params: %s", params)
                
                response = await self.client.chat.completions.create(
                    messages=chat_messages,
                    **params
                )
                return response.choices[0].message

            except Exception as e:
                error_str = str(e).lower()
                if ("timeout" in error_str or "500" in error_str) and attempt < self.retries:
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Alibaba API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")


class AsyncTencentClient:
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None,
        retries: int = 3,
        delay: int = 3
    ):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.retries = retries
        self.delay = delay
        self.logger = logging.getLogger(__name__)

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.hunyuan.cloud.tencent.com/v1"
        )

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]

        for attempt in range(1, self.retries + 1):
            try:
                params = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature
                }
                # Remove None values
                params = {k: v for k, v in params.items() if v is not None}
                
                self.logger.info("🤖 Invoking Tencent model with params: %s", params)
                
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    messages=chat_messages,
                    **params
                )
                return response.choices[0].message
            except Exception as e:
                if attempt < self.retries and ("timeout" in str(e).lower() or "500" in str(e).lower()):
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Tencent API error: {str(e)}")
