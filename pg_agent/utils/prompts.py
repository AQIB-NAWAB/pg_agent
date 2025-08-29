"""Utility functions for handling prompt files and paths."""

from pathlib import Path
from typing import Optional


def get_prompt_path(prompt_name: str) -> Path:
    """Gets the path to a prompt file in the prompts directory.
    
    Args:
        prompt_name: Name of the prompt file (e.g., "gen_basic_tests.txt")
        
    Returns:
        Path to the prompt file
    """
    # Get the prompts directory relative to the current file location
    current_file = Path(__file__)
    prompts_dir = current_file.parent.parent / "prompts"
    return prompts_dir / prompt_name


def get_refinement_prompt_path(base_prompt_name: str) -> Optional[Path]:
    """Gets the path to a refinement prompt file if it exists.
    
    Args:
        base_prompt_name: Base prompt name (e.g., "gen_basic_tests.txt")
        
    Returns:
        Path to the refinement prompt file, or None if it doesn't exist
    """
    if not base_prompt_name.endswith(".txt"):
        return None
        
    refinement_name = base_prompt_name.replace(".txt", "_refine.txt")
    refinement_path = get_prompt_path(refinement_name)
    
    if refinement_path.exists():
        return refinement_path
    return None


def prompt_exists(prompt_name: str) -> bool:
    """Checks if a prompt file exists.
    
    Args:
        prompt_name: Name of the prompt file
        
    Returns:
        True if the prompt file exists, False otherwise
    """
    return get_prompt_path(prompt_name).exists()
