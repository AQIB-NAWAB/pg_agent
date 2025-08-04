import os
import asyncio
import httpx
from openai import AsyncOpenAI
from volcenginesdkarkruntime import Ark

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


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
        thinking_budget: int = 38912,  # Added the class Argument for the value
        retries: int = 3,
        delay: int = 3,
        timeout: float = 600.0
    ):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget  # STORE IT
        self.retries = retries
        self.delay = delay
        self.timeout = timeout

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        )

    async def ainvoke(self, messages):
        chat_messages = [{"role": "user", "content": m.content} for m in messages]

        for attempt in range(1, self.retries + 1):
            try:
                if self.enable_thinking:
                    stream = await self.client.chat.completions.create(
                        model=self.model,
                        messages=chat_messages,
                        temperature=self.temperature,
                        stream=True,
                        extra_body={
                            "enable_thinking": True,
                            "thinking_budget": self.thinking_budget 
                        }
                    )
                    content = ""
                    async for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content += chunk.choices[0].delta.content
                    return type("Response", (), {"content": content})

                else:
                    response = await self.client.chat.completions.create(
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
                raise RuntimeError(f"Qwen API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")
