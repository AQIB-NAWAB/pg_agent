import os
import json
from pathlib import Path
from dotenv import load_dotenv

_settings_cache = None  # Cache for loaded settings

def get_settings():
    """Load and return PG-Agent settings from JSON."""
    global _settings_cache
    if _settings_cache is None:
        settings_path = Path(__file__).parent.parent.parent / "pg_agent_settings.json"
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        with open(settings_path, "r", encoding="utf-8") as f:
            _settings_cache = json.load(f)
    return _settings_cache


def get_available_models(script_name: str):
    """Return a list of all model names from model_config."""
    settings = get_settings()
    return settings[script_name]["models"]


def default_model(script_name: str):
    """Return the global default model from settings or the first available."""
    settings = get_settings()
    return settings[script_name]["default_model"]


def require_env(key: str) -> str:
    """
    Return the value of an environment variable, or raise an error if not set.
    """
    value = os.getenv(key)
    if value is None:
        raise EnvironmentError(f"Environment variable {key} is not set.")
    return value


def load_env(model, provider = ""):
    """
    Load environment variables and return the model configuration from settings JSON.
    """

    load_dotenv()

    settings = get_settings()
    models_config = settings.get("model_config", {})

    if not provider or provider == "default":
        for provider_name, provider_data in models_config.items():
            if model in provider_data.get("models", {}):
                provider = provider_name
                if provider_data.get("default"):
                    break

    if not provider or provider == "default":
        raise ValueError(f"Unsupported model: {model}")
    
    provider_config = models_config[provider]
    config = provider_config["models"][model]

    if "model" not in config:
        config["model"] = model
    if "parameters" not in config:
        config["parameters"] = {}

    config["api_key"] = require_env(provider_config.get("api_key_env"))
    config["provider"] = provider

    return config
