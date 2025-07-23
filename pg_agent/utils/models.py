import os
import asyncio
import httpx
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


# ========= Custom Async LLM Wrappers =========

class ChatBytedance:
    def __init__(self, model: str, api_key: str, temperature: float = 0.5, retries: int = 3, delay: int = 3):
        self.model = model
        self.client = Ark(api_key=api_key)
        self.temperature = temperature
        self.retries = retries
        self.delay = delay

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]
        for attempt in range(1, self.retries + 1):
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=chat_messages,
                    temperature=self.temperature,
                )
                return response.choices[0].message
            except Exception as e:
                error_str = str(e).lower()
                if ("timeout" in error_str or "500" in error_str) and attempt < self.retries:
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Doubao API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")


class ChatAlibaba:
    def __init__(
        self,
        model: str,
        api_key: str,
        temperature: float = 0.5,
        enable_thinking: bool = False,
        thinking_budget: int = 38912,
        retries: int = 3,
        delay: int = 3,
        timeout: float = 600.0
    ):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.retries = retries
        self.delay = delay
        self.timeout = timeout

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

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=chat_messages,
                    temperature=self.temperature,
                    stream=False,
                    extra_body=extra_body
                )
                return response.choices[0].message

            except Exception as e:
                error_str = str(e).lower()
                if ("timeout" in error_str or "500" in error_str) and attempt < self.retries:
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Qwen API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")


class ChatHunyuan:
    def __init__(self, model: str, api_key: str, temperature: float = 0.5, retries: int = 3, delay: int = 3):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.retries = retries
        self.delay = delay

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.hunyuan.cloud.tencent.com/v1"
        )

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]

        for attempt in range(1, self.retries + 1):
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=chat_messages,
                    temperature=self.temperature,
                    extra_body={"enable_enhancement": True},
                )
                return response.choices[0].message
            except Exception as e:
                if attempt < self.retries and ("timeout" in str(e).lower() or "500" in str(e).lower()):
                    await asyncio.sleep(self.delay * attempt)
                    continue
                raise RuntimeError(f"Hunyuan API error: {str(e)}")
