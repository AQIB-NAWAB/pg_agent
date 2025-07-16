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
    
    # If no topics provided, select random topics
    if not state.get('topics'):
        topics_path = Path(__file__).parent.parent.parent / "topics.json"
        all_topics = json.loads(topics_path.read_text(encoding="utf-8"))
        all_topic_choices = []
        for top_level_value in all_topics.values():
            if isinstance(top_level_value, dict):
                for category_list in top_level_value.values(): all_topic_choices.extend(category_list)
            elif isinstance(top_level_value, list):
                all_topic_choices.extend(top_level_value)
        selected_topics = random.sample(all_topic_choices, k=random.randint(1, 2))
        topics = ", ".join(selected_topics)
        state['topics'] = topics

    return state 