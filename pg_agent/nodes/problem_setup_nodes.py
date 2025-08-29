import os
import json
import random
import shutil
from pathlib import Path
from typing import TypedDict, Optional

class ProblemSetupState(TypedDict):
    """State for the problem setup workflow."""
    output_dir: str
    topics: Optional[str]

def _copy_if_not_exists(src: Path, dst: Path):
    """Copy directory tree, but only copy files that don't exist in destination."""
    dst.mkdir(parents=True, exist_ok=True)
    
    for item in src.iterdir():
        dst_item = dst / item.name
        if item.is_dir():
            _copy_if_not_exists(item, dst_item)
        elif not dst_item.exists():
            shutil.copy2(item, dst_item)

def setup_problem_directory(state: ProblemSetupState) -> ProblemSetupState:
    """Non-interactive setup of problem directory."""
    output_path = Path(state['output_dir'])
    template_path = Path(__file__).parent.parent.parent / "repo_template"
    if not template_path.exists():
        raise FileNotFoundError(f"Template directory not found at: {template_path}")
    
    # Copy template files that don't exist
    _copy_if_not_exists(template_path, output_path)
    
    return state 