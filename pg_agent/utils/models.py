import os
import re
import asyncio
import httpx
import logging
import aiofiles
from openai import AsyncOpenAI
from volcenginesdkarkruntime import AsyncArk
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

    # Shared progress state across instances
    _progress = {}
    _progress_lock = asyncio.Lock()
    _progress_header_printed = False

    @classmethod
    async def update_progress(cls, run_id, stage, reasoning_len, response_len):
        async with cls._progress_lock:
            cls._progress[run_id] = {
                'stage': stage,
                'reasoning_len': reasoning_len,
                'response_len': response_len
            }
            
            # Print header only once
            if not cls._progress_header_printed:
                print("Generation Progress:")
                cls._progress_header_printed = True
                return  # Return after first header print
            
            # Save cursor position and move back to progress section
            print("\0337", end="")  # Save cursor
            print(f"\033[{len(cls._progress) + 2}A", end="")  # Move up to progress section (+2 for header and blank line)
            
            # Print progress
            print("\033[K")  # Clear header line
            print("Generation Progress:")
            for rid in sorted(cls._progress.keys()):
                p = cls._progress[rid]
                print(f"\033[KRun {rid:2d}: {p['stage']:<10} | Reasoning: {p['reasoning_len']:5d} | Response: {p['response_len']:5d} chars")
            
            # Restore cursor position
            print("\0338", end="", flush=True)  # Restore cursor

    async def get_completion_params(self, messages, stream=True):
        """Get provider-specific completion parameters. Override in subclasses."""
        chat_messages = [{"role": "user", "content": m.content} for m in messages]
        params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
            "messages": chat_messages
        }
        return {k: v for k, v in params.items() if v is not None}

    def is_async_client(self):
        """Check if the client is async. Override in subclasses if needed."""
        return isinstance(self.client, AsyncOpenAI)

    async def create_completion(self, params):
        """Create completion using provider-specific client."""
        if self.is_async_client():
            return await self.client.chat.completions.create(**params)
        else:
            return await asyncio.to_thread(
                self.client.chat.completions.create,
                **params
            )

    async def process_chunk(self, chunk, response_f, reasoning_f, run_id, current_lengths=None):
        """Process a chunk from the stream with common handling."""
        if not chunk.choices:
            if hasattr(chunk, 'usage'):
                self.logger.debug("Usage: %s", chunk.usage)
            return None

        if current_lengths is None:
            current_lengths = {'reasoning': 0, 'response': 0}
            
        delta = chunk.choices[0].delta
        result = {
            'full_content': '',
            'reasoning_content': '',
        }
 
        # Handle reasoning content (for models that support it)
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if reasoning_f:
                await reasoning_f.write(delta.reasoning_content)
                await reasoning_f.flush()
            result['reasoning_content'] = delta.reasoning_content
            current_lengths['reasoning'] += len(delta.reasoning_content)
            if run_id is not None:
                await self.update_progress(run_id, "Reasoning", current_lengths['reasoning'], current_lengths['response'])
        
        # Handle regular content
        if hasattr(delta, "content") and delta.content:
            if response_f:
                await response_f.write(delta.content)
                await response_f.flush()
            result['full_content'] = delta.content
            current_lengths['response'] += len(delta.content)
            if run_id is not None:
                await self.update_progress(run_id, "Responding", current_lengths['reasoning'], current_lengths['response'])
        
        return result

    async def ainvoke(self, messages, response_file, reasoning_file, run_id, stream=True, debug=False):
        """Generic implementation of async invocation with progress tracking."""

        # Initialize tracking variables
        full_content = ""
        reasoning_content = ""
        current_lengths = {'reasoning': 0, 'response': 0}

        # Initialize progress
        await self.update_progress(run_id, "Starting", 0, 0)

        try:
            params = await self.get_completion_params(messages, stream)
            self.logger.debug("🤖 Invoking %s with params: %s", self.model, params)
            
            if stream:
                stream_response = await self.create_completion(params)
                
                # Process the streaming response
                response_f = None
                reasoning_f = None
                debug_f = None
                
                try:
                    # Open files
                    response_f = await aiofiles.open(response_file, 'w', encoding='utf-8')
                    reasoning_f = await aiofiles.open(reasoning_file, 'w', encoding='utf-8')
                    
                    # Create debug file if debug is enabled
                    if debug:
                        debug_file = str(response_file).replace('.md', '.raw_chunks.txt')
                        debug_f = await aiofiles.open(debug_file, 'w', encoding='utf-8')
                        await debug_f.write(f"=== Raw Chunks Debug for {self.model} ===\n")
                        await debug_f.write(f"Run ID: {run_id}\n")
                        await debug_f.write(f"Response file: {response_file}\n")
                        await debug_f.write(f"Reasoning file: {reasoning_file}\n")
                        await debug_f.write("=" * 50 + "\n\n")
                    
                    # Initialize content accumulators
                    accumulated_reasoning = ""
                    accumulated_response = ""
                    chunk_count = 0
                    
                    async for chunk in stream_response:
                        chunk_count += 1
                        
                        # Write chunk to debug file if available
                        if debug and debug_f:
                            await debug_f.write(f"--- Chunk {chunk_count} ---\n")
                            await debug_f.write(f"Chunk: {chunk}\n")
                            await debug_f.write("\n")
                            await debug_f.flush()
                        
                        result = await self.process_chunk(chunk, response_f, reasoning_f, run_id, current_lengths)
                        if result:
                            # Accumulate content for final return
                            if result.get('reasoning_content'):
                                accumulated_reasoning += result.get('reasoning_content')
                            if result.get('full_content'):
                                accumulated_response += result.get('full_content')
                            
                            # Update tracking variables
                            full_content = accumulated_response
                            reasoning_content = accumulated_reasoning
                
                finally:
                    # Close files
                    await response_f.flush()
                    await response_f.close()
                    await reasoning_f.flush()
                    await reasoning_f.close()
                    if debug and debug_f:
                        await debug_f.write(f"\n=== End of chunks (total: {chunk_count}) ===\n")
                        await debug_f.write(f"Final accumulated reasoning length: {len(accumulated_reasoning)}\n")
                        await debug_f.write(f"Final accumulated response length: {len(accumulated_response)}\n")
                        await debug_f.flush()
                        await debug_f.close()
                    
                # Update final progress with accumulated lengths
                await self.update_progress(run_id, "Completed", current_lengths['reasoning'], current_lengths['response'])
                
                # Return a message-like object with both content types
                return type('Message', (), {
                    'content': full_content,
                    'reasoning_content': reasoning_content
                })()
            else:
                response = await self.create_completion(params)
                return response.choices[0].message
        except Exception as e:
            # Keep the current lengths even in case of error
            await self.update_progress(run_id, "Error", current_lengths['reasoning'], current_lengths['response'])
            raise RuntimeError(f"API error: {getattr(e, 'status_code', 'N/A')} - {str(e)}")


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

class AsyncBytedanceClient(AsyncLLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            env_key="BYTEDANCE_API_KEY",  # Not used since we pass api_key directly
            base_url="",  # Not used for Ark client
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=600.0,
        )
        self.client = AsyncArk(api_key=api_key)

    async def create_completion(self, params):
        """Override to use AsyncArk client."""
        messages = params.pop("messages")
        return await self.client.chat.completions.create(
            messages=messages,
            **params
        )


class AsyncAlibabaClient(AsyncLLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None,
        enable_thinking: bool = False,
        thinking_budget: int = 38912,
        timeout: float = 600.0
    ):
        # Determine base URL based on model type
        self.is_fireworks = model.startswith("accounts/fireworks/models/")
        base_url = (
            "https://api.fireworks.ai/inference/v1"
            if self.is_fireworks
            else "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )

        super().__init__(
            model=model,
            api_key=api_key,
            env_key="ALIBABA_API_KEY",  # Not used since we pass api_key directly
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

    async def get_completion_params(self, messages, stream=True):
        """Get provider-specific completion parameters."""
        params = await super().get_completion_params(messages, stream)
        
        # Add thinking mode parameters for Alibaba models
        if not self.is_fireworks and self.enable_thinking:
            params["extra_body"] = {
                "enable_thinking": True,
                "thinking_budget": self.thinking_budget
            }
        
        return params

    def is_async_client(self):
        """Both Fireworks and Alibaba clients are async."""
        return True

    def get_reasoning_key(self):
        """Get the key used for reasoning/thinking content."""
        return "thinking_content" if not self.is_fireworks else "reasoning_content"

    async def process_chunk(self, chunk, response_f, reasoning_f, run_id, current_lengths=None):
        """Override to handle different reasoning content key names."""
        if not chunk.choices:
            return await super().process_chunk(chunk, response_f, reasoning_f, run_id, current_lengths)
            
        # Replace reasoning_content with the appropriate key for this provider
        delta = chunk.choices[0].delta
        reasoning_key = self.get_reasoning_key()
        if hasattr(delta, reasoning_key):
            # Temporarily map to reasoning_content for base class handling
            setattr(delta, "reasoning_content", getattr(delta, reasoning_key))
            
        return await super().process_chunk(chunk, response_f, reasoning_f, run_id, current_lengths)


class AsyncTencentClient(AsyncLLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = None,
        temperature: float = None
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            env_key="TENCENT_API_KEY",  # Not used since we pass api_key directly
            base_url="https://api.hunyuan.cloud.tencent.com/v1",
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=600.0,
        )
        # Use AsyncOpenAI instead of OpenAI for consistent async behavior
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://api.hunyuan.cloud.tencent.com/v1",
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(600.0))
        )
