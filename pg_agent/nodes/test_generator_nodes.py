import os
import re
import json
import logging
from pathlib import Path
from typing import TypedDict, Optional, List, Tuple, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.parsing import parse_test_cases

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
    mode: Literal["small", "stress", "validator"]  # Current generation mode

class SimpleTestGenerationState(TypedDict):
    """State for simple test case generation workflow."""
    output_dir: str
    problem_statement: str
    test_cases: List[Tuple[str, str]]

def _extract_cpp_code(response_content: str) -> str:
    """Parses the LLM's response to extract only the C++ code."""
    match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response_content)
    if match: return match.group(1).strip()
    return response_content.strip()

def get_llm_client():
    """Creates an OpenAI client, reading the key from the environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o4-mini", api_key=api_key)

def load_context_node(state: TestCaseGeneratorState) -> dict:
    """Loads the problem statement and bruteforce solution if needed.
    
    Only loads bruteforce solution for test generators (small/stress).
    For validator, or when not refining, only loads problem statement.
    """
    print(f"--- Loading context from: {state['problem_dir_path']} ---")
    problem_dir = Path(state['problem_dir_path'])
    
    # Always load problem statement
    problem_statement_path = problem_dir / "problem_statement.md"
    if not problem_statement_path.exists():
        raise FileNotFoundError(f"Problem statement not found at {problem_statement_path}")
    problem_statement = problem_statement_path.read_text(encoding="utf-8")
    print("Loaded problem statement")
    
    # Only load bruteforce solution for test generators
    bruteforce_code = ""
    if state["mode"] in ["small", "stress"]:
        automation_dir = problem_dir / "automation"
        settings_path = automation_dir / "automation_settings.json"
        
        if not settings_path.exists():
            raise FileNotFoundError("automation_settings.json not found. Please run bruteforce generator first.")
            
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        bf_version = settings.get("bruteforceSolutionVersion", -1)
        
        if bf_version == -1:
            raise FileNotFoundError("Bruteforce solution not found. Please run bruteforce generator first.")
            
        bruteforce_path = automation_dir / "bruteForceSol" / f"bruteforceSolution_v{bf_version}.cpp"
        bruteforce_code = bruteforce_path.read_text(encoding="utf-8")
        print("Loaded bruteforce solution")
    
    return {
        "problem_statement": problem_statement,
        "bruteforce_code": bruteforce_code
    }

def generate_simple_test_cases(state: SimpleTestGenerationState) -> SimpleTestGenerationState:
    """Generate additional test cases beyond examples."""
    print("--- Generating simple test cases ---")
    prompt_path = Path(__file__).parent.parent / "prompts/generate_examples.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    chain = prompt | get_llm_client()
    response = chain.invoke({"problem_statement": state["problem_statement"]})
    logger.info("Generated test cases from LLM")
    
    test_cases = parse_test_cases(response.content)
    logger.info("Parsed %d test cases", len(test_cases))

    # Save the test cases
    test_cases_dir = Path(state['output_dir']) / "test_cases"
    test_cases_dir.mkdir(exist_ok=True)
    # Clean up existing test files
    for f in test_cases_dir.glob("test_*.in"):
        f.unlink()
    for f in test_cases_dir.glob("test_*.out"):
        f.unlink()
    
    for i, (input_data, output_data) in enumerate(test_cases, 1):
        input_path = test_cases_dir / f"test_{i}.in"
        output_path = test_cases_dir / f"test_{i}.out"
        input_path.write_text(input_data, encoding="utf-8")
        output_path.write_text(output_data, encoding="utf-8")
        logger.debug("Saved test case %d to %s and %s", i, input_path, output_path)
    
    print(f"Generated and saved {len(test_cases)} test cases.")
    return {"test_cases": test_cases}

def _create_generation_node(prompt_file_name: str, output_key: str, version_key: str):
    """A factory to create a node that generates test case generator scripts."""
    def generation_node(state: TestCaseGeneratorState) -> dict:
        print(f"--- Generating: {output_key} ---")
        
        # Load settings
        automation_dir = Path(state['problem_dir_path']) / "automation"
        settings_path = automation_dir / "automation_settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        current_version = settings.get(version_key, -1)
        
        # If in refine mode, load existing code
        existing_code = None
        if state["refine_mode"] and current_version >= 0:
            file_prefix = version_key.replace("Version", "")
            existing_path = automation_dir / "testcaseGenScript" / f"{file_prefix}_v{current_version}.cpp"
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
            "bruteforce_code": state["bruteforce_code"] if state["mode"] in ["small", "stress"] else ""
        }
        if state["refine_mode"] and existing_code:
            variables["existing_code"] = existing_code
            variables["user_feedback"] = state["user_feedback"]
            
        response = chain.invoke(variables)
        code = _extract_cpp_code(response.content)
        
        # Save the generated code
        new_version = current_version + 1 if current_version >= 0 else 0
        script_dir = automation_dir / "testcaseGenScript"
        script_dir.mkdir(parents=True, exist_ok=True)
        
        file_prefix = version_key.replace("Version", "")
        final_path = script_dir / f"{file_prefix}_v{new_version}.cpp"
        final_path.write_text(code, encoding="utf-8")
        
        settings[version_key] = new_version
        settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
        
        action = "Refined" if state["refine_mode"] and existing_code else "Created"
        print(f"{action} version {new_version} at: {final_path}")
        return {output_key: str(final_path)}

    return generation_node

# Create the generator nodes
gen_small_tests_node = _create_generation_node(
    "gen_small_tests.txt", "small_test_gen_path", "smallTestcaseGeneratorVersion"
)
gen_stress_tests_node = _create_generation_node(
    "gen_stress_tests.txt", "stress_test_gen_path", "stressTestcaseGeneratorVersion"
)
gen_validator_node = _create_generation_node(
    "gen_validator.txt", "validator_path", "testcaseValidatorVersion"
) 