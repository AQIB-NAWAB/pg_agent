import os
import re
import json
import logging
from pathlib import Path
from typing import TypedDict, List, Tuple, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.parsing import parse_test_cases
from ..utils.structure import get_problem_paths

logger = logging.getLogger(__name__)

class SimpleTestGenerationState(TypedDict):
    """State for simple test case generation workflow."""
    output_dir: str
    problem_statement: str
    test_cases: List[Tuple[str, str]]
    parse_only: bool  # Whether to only parse tests from latest response

def get_llm_client():
    """Creates an OpenAI client, reading the key from the environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o3", api_key=api_key)

def _get_latest_manual_tests_response(problem_dir: Path) -> Optional[str]:
    """Gets the latest manual tests response if it exists.
    
    Args:
        problem_dir: Path to the problem directory
        
    Returns:
        The content of the latest response file, or None if no responses exist
    """
    settings_path = problem_dir / "automation/automation_settings.json"
    if not settings_path.exists():
        logger.warning("No automation_settings.json found at: %s", settings_path)
        return None
        
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    version = settings.get("manualTestsVersion", -1)
    logger.info("Found manual tests version: %d", version)
    
    if version == -1:
        logger.warning("No manual tests version found in settings")
        return None
        
    response_path = problem_dir / "automation/manual_tests" / f"manual_tests_v{version}.txt"
    if not response_path.exists():
        logger.error("Response file not found at: %s", response_path)
        return None
        
    logger.info("Reading response from: %s", response_path)
    content = response_path.read_text(encoding="utf-8")
    return content

def _save_manual_tests_response(problem_dir: Path, response_content: str) -> Tuple[int, Path]:
    """Saves the raw LLM response and returns the version number and file path.
    
    Args:
        problem_dir: Path to the problem directory
        response_content: The raw LLM response to save
        
    Returns:
        Tuple containing:
        - The version number of the saved response
        - The path where the response was saved
    """
    automation_dir = problem_dir / "automation"
    automation_dir.mkdir(exist_ok=True)
    logger.info("Using automation directory: %s", automation_dir)
    
    # Load or create settings
    settings_path = automation_dir / "automation_settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        logger.info("Creating new settings file at: %s", settings_path)
        settings = {"manualTestsVersion": -1}
    
    # Increment version
    version_key = "manualTestsVersion"
    new_version = settings.get(version_key, -1) + 1
    logger.info("Creating new version: %d", new_version)
    
    # Save response
    manual_tests_dir = automation_dir / "manual_tests"
    manual_tests_dir.mkdir(parents=True, exist_ok=True)
    final_path = manual_tests_dir / f"manual_tests_v{new_version}.txt"
    final_path.write_text(response_content, encoding="utf-8")
    logger.info("Saved response content (%d characters) to: %s", len(response_content), final_path)
    
    # Update settings
    settings[version_key] = new_version
    settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
    logger.info("Updated settings with new version")
    
    return new_version, final_path

def generate_simple_test_cases(state: SimpleTestGenerationState) -> SimpleTestGenerationState:
    """Generate additional test cases beyond examples."""
    paths = get_problem_paths(state['output_dir'])
    logger.info("Working with problem directory: %s", paths.root)
    
    # If parse_only is True, try to get latest response
    if state.get("parse_only"):
        print("--- Parsing tests from latest response ---")
        response_content = _get_latest_manual_tests_response(paths.root)
        if not response_content:
            raise ValueError("No existing manual tests response found. Run without --parse first.")
    else:
        print("--- Generating simple test cases ---")
        prompt_path = Path(__file__).parent.parent / "prompts/gen_manual_tests.txt"
        logger.info("Using prompt from: %s", prompt_path)
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        chain = prompt | get_llm_client()
        response = chain.invoke({"problem_statement": state["problem_statement"]})
        logger.info("Generated test cases from LLM")
        
        # Save the raw response
        response_content = response.content
        new_version, response_path = _save_manual_tests_response(paths.root, response_content)
        print(f"Saved raw LLM response version {new_version} to: {response_path}")
    
    # Log the first few characters of the response for debugging
    preview_length = min(200, len(response_content))
    logger.info("Response preview: %s...", response_content[:preview_length])
    
    test_cases = parse_test_cases(response_content)
    logger.info("Parsed %d test cases", len(test_cases))

    # Save the test cases using ProblemPaths
    paths.test_cases.mkdir(exist_ok=True)
    logger.info("Saving test cases to: %s", paths.test_cases)
    
    # Clean up existing test files
    for f in paths.test_cases.glob("test_*.in"):
        logger.info("Removing old test file: %s", f)
        f.unlink()
    for f in paths.test_cases.glob("test_*.out"):
        logger.info("Removing old test file: %s", f)
        f.unlink()
    
    for i, (input_data, output_data) in enumerate(test_cases, 1):
        input_path = paths.test_cases / f"test_{i}.in"
        output_path = paths.test_cases / f"test_{i}.out"
        input_path.write_text(input_data, encoding="utf-8")
        output_path.write_text(output_data, encoding="utf-8")
        logger.info("Saved test case %d to %s and %s", i, input_path, output_path)
        logger.info("Input: %s", input_data[:100] + "..." if len(input_data) > 100 else input_data)
        logger.info("Output: %s", output_data[:100] + "..." if len(output_data) > 100 else output_data)
    
    print(f"Generated and saved {len(test_cases)} test cases.")
    return {"test_cases": test_cases} 