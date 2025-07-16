import json
from pathlib import Path

def get_default_problem_dir():
    """Get the default problem directory from settings."""
    settings_path = Path(__file__).parent.parent.parent / "pg_agent_settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        # Get the relative path from settings
        default_dir = settings.get("problem_directory", "")
        # Resolve it relative to current directory
        resolved_path = Path.cwd() / default_dir
        # Resolve any .. or . in the path
        default_dir = str(resolved_path.resolve())
        return default_dir
    except Exception as e:
        print(f"Warning: Could not read default problem directory from settings: {e}")
        return None 