import os
import asyncio
import httpx
import logging, json
import aiofiles
from openai import AsyncOpenAI
from volcenginesdkarkruntime import AsyncArk
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Optional

logger = logging.getLogger(__name__)


def get_llm(
    model_config: dict
):
    """
    Returns a LangChain-compatible LLM instance based on model name or config dict.
    """
    common_params = {
        "model": model_config["model"],
        "api_key": model_config["api_key"],
        "max_tokens": model_config["parameters"].get("max_tokens", None)
    }
    common_params = {k: v for k, v in common_params.items() if v is not None}

    # Instantiate the correct client
    if model_config["provider"] == "openai":
        return ChatOpenAI(**common_params)
    elif model_config["provider"] == "anthropic":
        return ChatAnthropic(**common_params)
    elif model_config["provider"] == "google":
        return ChatGoogleGenerativeAI(**common_params)
    else:
        raise ValueError(f"Unsupported model: {model_config['model']}")

def get_async_llm(model_config):
    """Get an async LLM client instance based on the model type.
    
    Args:
        model_config: The model configuration dictionary
        
    Returns:
        An instance of AsyncLLMClient or its subclasses
        
    Raises:
        ValueError: If the model type is not supported
    """
    common_params = {
        "model": model_config["model"],
        "api_key": model_config["api_key"],
    }
    common_params = {k: v for k, v in common_params.items() if v is not None}
    parameters = model_config["parameters"]

    if model_config["provider"] == "fireworks" or model_config["provider"] == "dashscope":
        return AsyncAlibabaClient(**common_params, parameters=parameters)
    elif model_config["provider"] == "bytedance":
        return AsyncBytedanceClient(**common_params, parameters=parameters)
    elif model_config["provider"] == "tencent":
        return AsyncTencentClient(**common_params, parameters=parameters)
    elif model_config["provider"] == "openai":
        return AsyncOpenAIClient(**common_params, parameters=parameters)
    elif model_config["provider"] == "anthropic":
        return AsyncAnthropicClient(**common_params, parameters=parameters)
    elif model_config["provider"] == "google":
        return AsyncGeminiClient(**common_params, parameters=parameters)
    else:
        raise ValueError(f"Unsupported model: {model_config['model']}")


class AsyncLLMClient:
    def __init__(self, model: str, api_key: str, base_url: str, parameters: dict = {}, timeout: float = 600.0):
        self.model = model
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        self.api_key = api_key
        if not self.api_key:
            raise ValueError(f"api_key not set.")

        if base_url:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url,
                http_client=httpx.AsyncClient(timeout=httpx.Timeout(timeout)),
            )

    async def get_completion_params(self, messages, stream=True):
        """Get provider-specific completion parameters. Override in subclasses."""
        chat_messages = [{"role": "user", "content": m.content} for m in messages]
        params = {
            "model": self.model,
            "stream": stream,
            "messages": chat_messages,
            **self.parameters
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

    async def process_chunk(self, chunk, response_f, reasoning_f, current_lengths: dict):
        """Process a chunk from the stream with common handling."""
        if not chunk.choices:
            if hasattr(chunk, 'usage'):
                self.logger.debug("Usage: %s", chunk.usage)
            return None

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
        
        # Handle regular content
        if hasattr(delta, "content") and delta.content:
            if response_f:
                await response_f.write(delta.content)
                await response_f.flush()
            result['full_content'] = delta.content
            current_lengths['response'] += len(delta.content)
        
        return result

    async def ainvoke(self, messages, response_file, reasoning_file, stream=True, context=None, callback=None, debug=False):
        """Generic implementation of async invocation with progress tracking."""

        full_content = ""
        reasoning_content = ""
        current_lengths = {'reasoning': 0, 'response': 0}

        try:
            params = await self.get_completion_params(messages, stream)
            self.logger.debug("🤖 Invoking %s with params: %s", self.model, params)
            
            if stream:
                if callback:
                    callback(context, {"stage": "Starting", "lengths": current_lengths})

                stream_response = await self.create_completion(params)
                
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
                        
                        result = await self.process_chunk(chunk, response_f, reasoning_f, current_lengths)
                        if callback:
                            callback(context, {"stage": "Responding", "lengths": current_lengths})
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
                    
                if callback:
                    callback(context, {"stage": "Completed", "lengths": current_lengths})
                
                return type('Message', (), {
                    'content': full_content,
                    'reasoning_content': reasoning_content
                })()
            else:
                response = await self.create_completion(params)
                return response.choices[0].message
        except Exception as e:
            if callback:
                callback(context, {"stage": "Error", "lengths": current_lengths})
            raise e


class AsyncOpenAIClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}, timeout: float = 600.0):
        super().__init__(model, api_key, parameters, "https://api.openai.com/v1", timeout)


class AsyncAnthropicClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}, timeout: float = 600.0):
        super().__init__(model, api_key, "https://api.anthropic.com/v1", parameters, timeout)


class AsyncBytedanceClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}):
        super().__init__(model, api_key, "", parameters, 600.0)
        self.client = AsyncArk(api_key=api_key)

    def is_async_client(self):
        return True


class AsyncAlibabaClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}, timeout: float = 600.0):
        # Determine base URL based on model type
        self.is_fireworks = model.startswith("accounts/fireworks/models/")
        base_url = (
            "https://api.fireworks.ai/inference/v1"
            if self.is_fireworks
            else "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        super().__init__(model, api_key, base_url, parameters, timeout)
        
    def is_async_client(self):
        """Both Fireworks and Alibaba clients are async."""
        return True

    def get_reasoning_key(self):
        """Get the key used for reasoning/thinking content."""
        return "reasoning_content" if self.is_fireworks else "thinking_content"

    async def process_chunk(self, chunk, response_f, reasoning_f, current_lengths: dict):
        """Override to handle different reasoning content key names."""
        if not chunk.choices:
            return await super().process_chunk(chunk, response_f, reasoning_f, current_lengths)
            
        # Replace reasoning_content with the appropriate key for this provider
        delta = chunk.choices[0].delta
        reasoning_key = self.get_reasoning_key()
        if hasattr(delta, reasoning_key):
            # Temporarily map to reasoning_content for base class handling
            setattr(delta, "reasoning_content", getattr(delta, reasoning_key))
            
        return await super().process_chunk(chunk, response_f, reasoning_f, current_lengths)


class AsyncTencentClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}):
        super().__init__(model, api_key, "https://api.hunyuan.cloud.tencent.com/v1", parameters, 600.0)


class AsyncGeminiClient(AsyncLLMClient):
    def __init__(self, model: str, api_key: str, parameters: dict = {}):
        self.logger = logging.getLogger(__name__)
        self.model = model
        self.api_key = api_key

        params = {
            "model": model,
            **parameters
        }
        params = {k: v for k, v in params.items() if v is not None}
        self.client = ChatGoogleGenerativeAI(
            api_key=api_key,
            **params
        )

    async def ainvoke(self, messages, response_file, reasoning_file, stream=True, context=None, callback=None, debug=False):
        chat_messages = [{"role": m.type, "content": m.content} for m in messages]

        if not stream:
            # Native async non-streaming call
            response = await self.client.ainvoke(chat_messages)

            async with aiofiles.open(response_file, "w", encoding="utf-8") as f:
                await f.write(response.content)

            if callback:
                callback(context, {"stage": "Completed", "lengths": {"reasoning": reasoning_len, "response": len(response.content)}})
            return response

        # Initialize progress at start
        if callback:
            callback(context, {"stage": "Starting", "lengths": {"reasoning": 0, "response": 0}})

        reasoning_len = 0
        response_len = 0

        # Streaming mode: use native async streaming
        async with aiofiles.open(response_file, "w", encoding="utf-8") as response_f:
            async for chunk in self.client.astream(chat_messages):
                chunk_content = chunk.content or ""
                await response_f.write(chunk_content)
                await response_f.flush()

                response_len += len(chunk_content)
                if callback:
                    callback(context, {"stage": "Responding", "lengths": {"reasoning": reasoning_len, "response": response_len}})

        if callback:
            callback(context, {"stage": "Completed", "lengths": {"reasoning": reasoning_len, "response": response_len}})

        return type('Message', (), {'content': await self._read_file(response_file)})()

    async def _read_file(self, file_path):
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
