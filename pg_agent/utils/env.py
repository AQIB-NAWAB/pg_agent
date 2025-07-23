import os
from dotenv import load_dotenv
__all__ = ["require_env", "load_env"]


def require_env(key: str) -> str:
    """Return the value of environment variable *key* or raise a clear error."""
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"Environment variable {key} is not set.")
    return value


def load_env(provider: str = None):
    load_dotenv()
    if provider == "fireworks":
        api_key = os.getenv("FIREWORKS_API_KEY")
        if not api_key:
            raise ValueError("FIREWORKS_API_KEY not found in .env")
        return {
            "qwen3-coder-480b-a35b-instruct": {
                "api_key": api_key,
                "model": "accounts/fireworks/models/qwen3-coder-480b-a35b-instruct",
            },
            "qwen3-235b-a22b-thinking-2507": {
                "api_key": api_key,
                "model": "accounts/fireworks/models/qwen3-235b-a22b-thinking-2507",
            }
        }
    
    # default dashscope-based loading
    return {
        "qwen3-coder-480b-a35b-instruct": {
            "api_key": os.getenv("DASHSCOPE_API_KEY"),
            "model": "qwen3-coder-480b-a35b-instruct",
        },
        "qwen3-235b-a22b-thinking-2507": {
            "api_key": os.getenv("DASHSCOPE_API_KEY"),
            "model": "qwen3-235b-a22b-thinking-2507",
        },
        "doubao-seed-1-6-thinking-250715": {
            "api_key": os.getenv("ARK_API_KEY"),
            "model": os.getenv("DUBAO_MODEL_NAME", "doubao-seed-1-6-thinking-250715"),
        },
        "hunyuan-t1-20250711": {
            "api_key": os.getenv("TENCENT_API_KEY"),
            "model": "hunyuan-t1-20250711",
        },
        "hunyuan-turbos-20250604": {
            "api_key": os.getenv("TENCENT_API_KEY"),
            "model": "hunyuan-turbos-20250604",
        },
    }
