import os
from dotenv import load_dotenv
__all__ = ["require_env", "load_env"]


def require_env(key: str) -> str:
    """Return the value of environment variable *key* or raise a clear error."""
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"Environment variable {key} is not set.")
    return value


def load_env(model: str, provider: str = None):
    """Load environment variables and return model configuration.
    
    Args:
        model: The model name to load configuration for
        provider: The provider to use for Qwen models (fireworks or dashscope)
    
    Returns:
        dict: Model configuration containing api_key and model name
    """
    load_dotenv()
    
    # Handle Qwen models with provider selection
    if model.startswith("qwen"):
        if provider == "fireworks":
            prefix = "accounts/fireworks/models/"
            
            # Define Qwen model configs with max_tokens for Fireworks
            model_configs = {
                "qwen3-coder-480b-a35b-instruct": {
                    "api_key": "FIREWORKS_API_KEY",
                    "model": prefix + "qwen3-coder-480b-a35b-instruct",
                    "max_tokens": 65536
                },
                "qwen3-235b-a22b-thinking-2507": {
                    "api_key": "FIREWORKS_API_KEY",
                    "model": prefix + "qwen3-235b-a22b-thinking-2507",
                    "max_tokens": 38912
                }
            }
        else:  # default to dashscope
            # Define Qwen model configs without max_tokens for Dashscope
            model_configs = {
                "qwen3-coder-480b-a35b-instruct": {
                    "api_key": "DASHSCOPE_API_KEY",
                    "model": "qwen3-coder-480b-a35b-instruct"
                },
                "qwen3-235b-a22b-thinking-2507": {
                    "api_key": "DASHSCOPE_API_KEY",
                    "model": "qwen3-235b-a22b-thinking-2507"
                }
            }
    else:
        # Handle other models
        model_configs = {
            "doubao-seed-1-6-thinking-250715": {
                "api_key": "ARK_API_KEY",
                "model": "doubao-seed-1-6-thinking-250715",
            },
            "hunyuan-t1-20250711": {
                "api_key": "TENCENT_API_KEY",
                "model": "hunyuan-t1-20250711",
                "max_tokens": 64000
            },
            "hunyuan-turbos-20250604": {
                "api_key": "TENCENT_API_KEY",
                "model": "hunyuan-turbos-20250604",
                "max_tokens": 16000
            },
            "claude-opus-4-20250514": {
                "api_key": "ANTHROPIC_API_KEY",
                "model": "claude-opus-4-20250514"
            },
            "claude-opus-4-1-20250805": {
                "api_key": "ANTHROPIC_API_KEY",
                "model": "claude-opus-4-1-20250805"
            },
            "claude-sonnet-4-20250514": {
                "api_key": "ANTHROPIC_API_KEY",
                "model": "claude-sonnet-4-20250514"
            },
            "o3": {
                "api_key": "OPENAI_API_KEY",
                "model": "o3"
            }
        }
    
    if model not in model_configs:
        raise ValueError(f"Unsupported model: {model}")
    
    # Resolve API key from environment
    config = model_configs[model].copy()
    config["api_key"] = require_env(config["api_key"])
    
    return config