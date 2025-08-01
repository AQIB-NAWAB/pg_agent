import os
from dotenv import load_dotenv
__all__ = ["require_env", "load_env"]


def require_env(key: str) -> str:
    """Return the value of environment variable *key* or raise a clear error."""
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"Environment variable {key} is not set.")
    return value


def load_env():
    load_dotenv()
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
        }
    }
