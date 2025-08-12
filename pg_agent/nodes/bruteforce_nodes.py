import os
import re
import json
import logging
from pathlib import Path
from typing import TypedDict, List, Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from ..utils.test_runner import find_test_cases, run_tests
from ..utils.structure import get_problem_paths
from ..utils.models import get_llm

# Configure logging
logger = logging.getLogger(__name__)

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
    llm_model: Optional[str]  

def load_problem_statement_node(state: BruteForceState) -> BruteForceState:
    """Loads the problem statement and example test cases."""
    print(f"--- Loading problem from: {state['problem_dir_path']} ---")
    problem_dir = Path(state['problem_dir_path'])

    problem_statement = (problem_dir / "problem_statement.md").read_text(encoding="utf-8")
    
    # Find example test cases using the test runner utility
    test_cases_dir = problem_dir / "test_cases"
    examples = find_test_cases(test_cases_dir, small_test_cases=True)

    print(f"Loaded problem statement and {len(examples)} example test cases.")
    return {
        **state,
        "problem_statement": problem_statement,
        "example_test_cases": examples
    }

def _load_previous_solution(problem_dir: Path, version: int) -> str:
    """Load the previous bruteforce solution code.
    
    Args:
        problem_dir: Path to the problem directory
        version: Current version number (will load version-1)
        
    Returns:
        Previous solution code or None if not found
    """
    if version <= 0:
        return None
        
    prev_version = version - 1
    solution_path = problem_dir / "automation" / "bruteForceSol" / f"bruteforceSolution_v{prev_version}.cpp"
    
    if solution_path.exists():
        return solution_path.read_text(encoding="utf-8")
    return None

def generate_or_refine_bruteforce_node(state: BruteForceState) -> BruteForceState:
    """Generates or refines bruteforce solution based on state."""
    is_refinement = state.get("human_feedback") is not None
    print(f"--- {'Refining' if is_refinement else 'Generating'} bruteforce solution ---")

    # Load appropriate prompt template
    model = state.get("llm_model", "o3")
    llm = get_llm(model)

    prompt_name = "refine_bruteforce.txt" if is_refinement else "gen_bruteforce.txt"
    prompt_path = Path(__file__).parent.parent / "prompts" / prompt_name
    prompt_template = prompt_path.read_text(encoding="utf-8")
    
    # Prepare prompt variables
    variables = {"problem_statement": state["problem_statement"]}
    
    if is_refinement:
        # Load previous solution
        problem_dir = Path(state['problem_dir_path'])
        previous_code = _load_previous_solution(problem_dir, state.get("iteration_count", 0))
        if previous_code is None:
            raise ValueError("No previous solution found for refinement")
        print("Loaded previous solution for refinement")

        # Load previous test failures if available
        prev_version = state.get("iteration_count", 0) - 1
        failures_path = problem_dir / "automation" / "bruteForceSol" / f"bruteforceSolution_v{prev_version}_failures.json"
        
        failures = []
        if failures_path.exists():
            failures = json.loads(failures_path.read_text(encoding="utf-8"))
            print(f"Loaded test failures from previous version {prev_version}")
        
        variables.update({
            "bruteforce_code": previous_code,
            "test_failures": json.dumps(failures, indent=2),
            "user_feedback": state.get("human_feedback", "")
        })
    
    # Create and debug the prompt
    prompt = ChatPromptTemplate.from_template(prompt_template)
    messages = prompt.format_messages(**variables)
    
    # Debug: Print the final rendered prompt
    logger.debug("Final rendered prompt:")
    logger.debug("=" * 80)
    for msg in messages:
        if isinstance(msg, HumanMessage):
            logger.debug(msg.content)
    logger.debug("=" * 80)
    
    # Create and invoke the chain
    chain = prompt | llm
    response = chain.invoke(variables)

    # Extract code from response
    code_match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response.content)
    code = code_match.group(1).strip() if code_match else response.content.strip()
    
    # Save the solution
    problem_dir = Path(state['problem_dir_path'])
    iteration = state.get("iteration_count", 0)
    solution_path = _save_bruteforce_solution(problem_dir, code, iteration)
    print(f"Saved solution version {iteration} to: {solution_path}")
    
    return {
        **state,
        "bruteforce_code": code,
        "final_bruteforce_path": str(solution_path)
    }

def test_bruteforce_node(state: BruteForceState) -> BruteForceState:
    """
    Tests the bruteforce solution, saves a detailed report for every run,
    and creates a separate failures-only report if any tests fail.
    """
    print("--- Testing bruteforce against examples ---")
    
    paths = get_problem_paths(str(state['problem_dir_path']))
    
    if not state["example_test_cases"]:
        print("Warning: No example test cases found to validate against.")
        return {**state, "test_failures": [], "final_verdict": "SUCCESS"}

    # Run tests to get the detailed report object
    test_report = run_tests(
        solution_code=state["bruteforce_code"],
        test_cases=state["example_test_cases"]
    )
    
    # Add code and test path to the main report 
    test_report["solution_code"] = state["bruteforce_code"]
    test_report["test_cases_path"] = str(paths.test_cases)
    
    iteration = state.get("iteration_count", 0)
    
    # Always save the full detailed report 
    full_report_path = paths.automation_bruteforce_dir / f"bruteforceSolution_v{iteration}_report.json"
    full_report_path.write_text(json.dumps(test_report, indent=2), encoding="utf-8")
    print(f"Full test report saved to: {full_report_path}")

    # Check for failures based on the summary
    summary = test_report.get("summary", {})
    failures = summary.get("status") == "ERROR" or summary.get("failures", 0) > 0
    
    if failures:
        # Create and save a separate, smaller failures-only report ---
        failed_cases = [res for res in test_report.get("results", []) if res["status"] != "PASSED"]
        failures_report = {
            "summary": test_report["summary"],
            "failed_tests": failed_cases,
            "solution_code": state["bruteforce_code"],
            "test_cases_path": str(paths.test_cases)
        }
        failures_path = paths.automation_bruteforce_dir / f"bruteforceSolution_v{iteration}_failures.json"
        failures_path.write_text(json.dumps(failures_report, indent=2), encoding="utf-8")
        print(f"Failures-only report saved to: {failures_path}")
        
        return {**state, "test_failures": failed_cases, "final_verdict": None}
    else:
        print("--- All examples PASSED. ---")
        paths.bruteforce_solution.write_text(state["bruteforce_code"], encoding="utf-8")
        print(f"Copied successful solution to: {paths.bruteforce_solution}")
        return {**state, "test_failures": [], "final_verdict": "SUCCESS"}

def _save_bruteforce_solution(problem_dir: Path, solution_code: str, version: int) -> Path:
    """Saves the bruteforce solution with specified version number.
    
    Args:
        problem_dir: Path to the problem directory
        solution_code: The C++ solution code to save
        version: Version number to use for the file
        
    Returns:
        Path where the solution was saved
    """
    automation_dir = problem_dir / "automation"
    automation_dir.mkdir(exist_ok=True)
    
    # Save solution
    bf_dir = automation_dir / "bruteForceSol"
    bf_dir.mkdir(parents=True, exist_ok=True)
    solution_path = bf_dir / f"bruteforceSolution_v{version}.cpp"
    solution_path.write_text(solution_code, encoding="utf-8")
    
    # Update settings
    settings_path = automation_dir / "automation_settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {}
    settings["bruteforceSolutionVersion"] = version
    settings_path.write_text(json.dumps(settings, indent=4), encoding="utf-8")
    
    return solution_path
