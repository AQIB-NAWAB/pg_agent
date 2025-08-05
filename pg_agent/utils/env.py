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
            api_key = os.getenv("FIREWORKS_API_KEY")
            if not api_key:
                raise ValueError("FIREWORKS_API_KEY not found in .env")
            
            model_mapping = {
                "qwen3-coder-480b-a35b-instruct": "accounts/fireworks/models/qwen3-coder-480b-a35b-instruct",
                "qwen3-235b-a22b-thinking-2507": "accounts/fireworks/models/qwen3-235b-a22b-thinking-2507"
            }
            return {
                "api_key": api_key,
                "model": model_mapping.get(model)
            }
        else:  # default to dashscope
            return {
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "model": model
            }
    
    # Handle other models
    model_configs = {
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
    
    if model not in model_configs:
        raise ValueError(f"Unsupported model: {model}")
    
    return model_configs[model]
