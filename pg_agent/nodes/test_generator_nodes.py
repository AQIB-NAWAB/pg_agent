import os
import re
import json
import logging
from pathlib import Path
from typing import TypedDict, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.structure import get_problem_paths

logger = logging.getLogger(__name__)

class TestCaseGeneratorState(TypedDict):
    """
    Represents the state for the Test Case Generation workflow.
    """
    problem_dir_path: str
    problem_statement: str
    bruteforce_code: str
    small_test_gen_path: Optional[str]
    stress_test_gen_path: Optional[str]
    validator_path: Optional[str]
    final_verdict: str
    refine_mode: bool  # Whether to refine existing generator
    user_feedback: str  # User feedback for refinement
    skip_small: bool  # Whether to skip small test generation
    skip_stress: bool  # Whether to skip stress test generation
    skip_validator: bool  # Whether to skip validator generation

def _extract_cpp_code(response_content: str) -> str:
    """Parses the LLM's response to extract only the C++ code."""
    match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response_content)
    if match: return match.group(1).strip()
    return response_content.strip()

def get_llm_client():
    """Creates an OpenAI client, reading the key from the environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o3", api_key=api_key)

def load_context_node(state: TestCaseGeneratorState) -> dict:
    """Loads the problem statement and bruteforce solution if needed.
    
    Only loads bruteforce solution for test generators (small/stress).
    For validator-only runs, or when not refining, only loads problem statement.
    """
    print(f"--- Loading context from: {state['problem_dir_path']} ---")
    paths = get_problem_paths(state['problem_dir_path'])
    
    # Always load problem statement
    if not paths.problem_statement.exists():
        raise FileNotFoundError(f"Problem statement not found at {paths.problem_statement}")
    problem_statement = paths.problem_statement.read_text(encoding="utf-8")
    print("Loaded problem statement")
    
    # Only load bruteforce solution if we're generating tests
    bruteforce_code = ""
    if not (state["skip_small"] and state["skip_stress"]):
        if not paths.automation_settings.exists():
            raise FileNotFoundError("automation_settings.json not found. Please run bruteforce generator first.")
            
        settings = json.loads(paths.automation_settings.read_text(encoding="utf-8"))
        bf_version = settings.get("bruteforceSolutionVersion", -1)
        
        if bf_version == -1:
            raise FileNotFoundError("Bruteforce solution not found. Please run bruteforce generator first.")
            
        bruteforce_path = paths.get_bruteforce_path(bf_version)
        bruteforce_code = bruteforce_path.read_text(encoding="utf-8")
        print("Loaded bruteforce solution")
    
    return {
        "problem_statement": problem_statement,
        "bruteforce_code": bruteforce_code
    }

def _create_generation_node(prompt_file_name: str, output_key: str, version_key: str, needs_bruteforce: bool = True):
    """A factory to create a node that generates test case generator scripts."""
    def generation_node(state: TestCaseGeneratorState) -> dict:
        print(f"--- Generating: {output_key} ---")
        
        # Load settings using ProblemPaths
        paths = get_problem_paths(state['problem_dir_path'])
        settings = paths.get_settings()
        current_version = settings.get(version_key, -1)
        
        # If in refine mode, load existing code
        existing_code = None
        if state["refine_mode"] and current_version >= 0:
            file_prefix = version_key.replace("Version", "")
            existing_path = paths.automation / "testcaseGenScript" / f"{file_prefix}_v{current_version}.cpp"
            if existing_path.exists():
                existing_code = existing_path.read_text(encoding="utf-8")
                print(f"Loaded existing version {current_version} for refinement")
            else:
                print(f"Warning: Could not find existing version {current_version} for refinement")
        
        # Determine which prompt to use based on mode
        if state["refine_mode"] and existing_code:
            # Use refinement prompt
            prompt_name = prompt_file_name.replace(".txt", "_refine.txt")
            if not (Path(__file__).parent.parent / "prompts" / prompt_name).exists():
                prompt_name = prompt_file_name  # Fallback to regular prompt
                print(f"Warning: Refinement prompt {prompt_name} not found, using regular prompt")
        else:
            prompt_name = prompt_file_name
            
        # Prepare prompt and invoke LLM
        prompt_path = Path(__file__).parent.parent / "prompts" / prompt_name
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        chain = prompt | get_llm_client()
        
        # Include existing code and feedback in prompt if refining
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code": state["bruteforce_code"] if needs_bruteforce else ""
        }
        if state["refine_mode"] and existing_code:
            variables["existing_code"] = existing_code
            variables["user_feedback"] = state["user_feedback"]
            
        response = chain.invoke(variables)
        code = _extract_cpp_code(response.content)
        
        # Save the generated code
        new_version = current_version + 1 if current_version >= 0 else 0
        script_dir = paths.automation / "testcaseGenScript"
        script_dir.mkdir(parents=True, exist_ok=True)
        
        file_prefix = version_key.replace("Version", "")
        final_path = script_dir / f"{file_prefix}_v{new_version}.cpp"
        final_path.write_text(code, encoding="utf-8")
        
        settings[version_key] = new_version
        paths.update_settings(settings)
        
        action = "Refined" if state["refine_mode"] and existing_code else "Created"
        print(f"{action} version {new_version} at: {final_path}")
        return {output_key: str(final_path)}

    return generation_node

# Create the generator nodes
gen_small_tests_node = _create_generation_node(
    "gen_small_tests.txt", "small_test_gen_path", "smallTestcaseGeneratorVersion", needs_bruteforce=True
)
gen_stress_tests_node = _create_generation_node(
    "gen_stress_tests.txt", "stress_test_gen_path", "stressTestcaseGeneratorVersion", needs_bruteforce=True
)
gen_validator_node = _create_generation_node(
    "gen_validator.txt", "validator_path", "testcaseValidatorVersion", needs_bruteforce=False
) 