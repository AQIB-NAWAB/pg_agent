import os
import re
import json
from pathlib import Path
from typing import TypedDict, List, Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..pipeline.sandbox.sandbox_utils import run_single_test

class BruteForceState(TypedDict):
    """State definition for the bruteforce solution generator."""
    problem_dir_path: str  # Path to the problem directory
    problem_statement: str
    example_test_cases: List[Dict[str, str]]
    bruteforce_code: Optional[str]
    test_failures: List[Dict[str, str]]
    iteration_count: int
    max_iterations: int
    human_feedback: Optional[str]
    final_verdict: Optional[str]  # Final status of the solution generation
    final_bruteforce_path: Optional[str]  # Path to the final saved solution

def load_problem_statement(state: BruteForceState) -> BruteForceState:
    """Loads the problem statement and example test cases."""
    print(f"--- Loading problem from: {state['problem_dir_path']} ---")
    problem_dir = Path(state['problem_dir_path'])
    
    problem_statement = (problem_dir / "problem_statement.md").read_text(encoding="utf-8")
    
    examples = []
    test_cases_dir = problem_dir / "test_cases"
    if test_cases_dir.exists():
        for in_file in sorted(test_cases_dir.glob("example_*.in")):
            out_file = in_file.with_suffix(".out")
            if out_file.exists():
                examples.append({
                    "input": in_file.read_text(encoding="utf-8"),
                    "output": out_file.read_text(encoding="utf-8").strip(),
                    "name": in_file.name
                })
    
    print(f"Loaded problem statement and {len(examples)} example test cases.")
    return {
        **state,
        "problem_statement": problem_statement,
        "example_test_cases": examples
    }

def generate_bruteforce(state: BruteForceState) -> BruteForceState:
    """Generates initial bruteforce solution."""
    print("--- Generating initial bruteforce solution ---")
    
    # Initialize OpenAI client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment.")
    llm = ChatOpenAI(model="o4-mini", api_key=api_key)
    
    # Load prompt template from file
    prompt_path = Path(__file__).parent.parent / "prompts" / "gen_bruteforce_from_problem.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    
    chain = ChatPromptTemplate.from_template(prompt_template) | llm
    response = chain.invoke({"problem_statement": state["problem_statement"]})
    
    # Extract code from response
    code_match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response.content)
    code = code_match.group(1).strip() if code_match else response.content.strip()
    
    return {
        **state,
        "bruteforce_code": code
    }

def _save_candidate_solution(problem_dir: Path, solution_code: str, iteration: int) -> Path:
    """Saves a candidate bruteforce solution without versioning.
    
    Args:
        problem_dir: Path to the problem directory
        solution_code: The C++ solution code to save
        iteration: Current iteration number
        
    Returns:
        Path where the candidate solution was saved
    """
    automation_dir = problem_dir / "automation"
    automation_dir.mkdir(exist_ok=True)
    
    # Save in a candidates subdirectory
    candidates_dir = automation_dir / "bruteForceSol" / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    
    # Save with iteration number
    candidate_path = candidates_dir / f"candidate_iteration_{iteration}.cpp"
    candidate_path.write_text(solution_code, encoding="utf-8")
    
    return candidate_path

def test_bruteforce(state: BruteForceState) -> BruteForceState:
    """Tests the bruteforce solution against example cases."""
    print("--- Testing bruteforce against examples ---")
    failures = []
    
    # Save the current candidate solution
    problem_dir = Path(state['problem_dir_path'])
    iteration = state.get("iteration_count", 0)
    candidate_path = _save_candidate_solution(problem_dir, state["bruteforce_code"], iteration)
    print(f"Saved candidate solution to: {candidate_path}")
    
    if not state["example_test_cases"]:
        print("Warning: No example test cases found to validate against.")
        return {
            **state,
            "test_failures": [],
            "iteration_count": iteration + 1
        }

    for i, example in enumerate(state["example_test_cases"]):
        print(f"  Running example #{i+1} ({example['name']})...")
        
        passed, actual_output = run_single_test(
            solution_code=state["bruteforce_code"],
            input_data=example["input"]
        )
        
        actual_output_stripped = actual_output.strip()

        if not passed or actual_output_stripped != example["output"]:
            failures.append({
                "example_number": i + 1,
                "input": example["input"],
                "expected_output": example["output"],
                "actual_output": actual_output_stripped
            })
    
    if failures:
        print(f"--- Test FAILED on {len(failures)} examples. ---")
    else:
        print("--- All examples PASSED. ---")
        
    return {
        **state,
        "test_failures": failures,
        "iteration_count": iteration + 1
    }

def refine_bruteforce(state: BruteForceState) -> BruteForceState:
    """Refines the bruteforce solution based on test failures."""
    print(f"--- Refining bruteforce solution (Attempt #{state['iteration_count']}) ---")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment.")
    llm = ChatOpenAI(model="o3", api_key=api_key)
    
    # Load prompt template from file
    prompt_path = Path(__file__).parent.parent / "prompts" / "refine_bruteforce_from_examples.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    
    chain = ChatPromptTemplate.from_template(prompt_template) | llm
    response = chain.invoke({
        "problem_statement": state["problem_statement"],
        "bruteforce_code": state["bruteforce_code"],
        "test_failures": json.dumps(state["test_failures"], indent=2)
    })
    
    code_match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response.content)
    code = code_match.group(1).strip() if code_match else response.content.strip()
    
    return {
        **state,
        "bruteforce_code": code
    }

def _save_bruteforce_solution(problem_dir: Path, solution_code: str) -> Tuple[int, Path]:
    """Saves the bruteforce solution to disk and returns the version number and file path.
    
    Args:
        problem_dir: Path to the problem directory
        solution_code: The C++ solution code to save
        
    Returns:
        Tuple containing:
        - The version number of the saved solution
        - The path where the solution was saved
    """
    automation_dir = problem_dir / "automation"
    automation_dir.mkdir(exist_ok=True)
    
    # Load or create settings
    settings_path = automation_dir / "automation_settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {"bruteforceSolutionVersion": -1}
    
    # Increment version
    version_key = "bruteforceSolutionVersion"
    new_version = settings.get(version_key, -1) + 1
    file_prefix = version_key.replace("Version", "")
    
    # Save solution
    bf_dir = automation_dir / "bruteForceSol"
    bf_dir.mkdir(parents=True, exist_ok=True)
    final_path = bf_dir / f"{file_prefix}_v{new_version}.cpp"
    final_path.write_text(solution_code, encoding="utf-8")
    
    # Update settings
    settings[version_key] = new_version
    settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
    
    return new_version, final_path

def save_solution(state: BruteForceState) -> BruteForceState:
    """Saves the final bruteforce solution."""
    print("--- Saving final bruteforce solution ---")
    
    # Save the solution and get version info
    problem_dir = Path(state['problem_dir_path'])
    new_version, final_path = _save_bruteforce_solution(problem_dir, state["bruteforce_code"])
    
    print(f"Saved new version {new_version} to: {final_path}")
    return {
        **state,
        "final_verdict": "SUCCESS",
        "final_bruteforce_path": str(final_path)
    }

def should_refine(state: BruteForceState) -> str:
    """Decision node: determines if we should continue refining."""
    print("--- Decision: Should Refine Bruteforce? ---")
    if state["test_failures"]:
        if state["iteration_count"] >= state["max_iterations"]:
            print(f"  -> Verdict: FAILED. Max iterations ({state['max_iterations']}) reached.")
            return "end_failure"
        print(f"  -> Verdict: FAILED. Continuing to refinement loop.")
        return "refine"
    else:
        print("  -> Verdict: PASSED. Proceed to save.")
        return "save" 