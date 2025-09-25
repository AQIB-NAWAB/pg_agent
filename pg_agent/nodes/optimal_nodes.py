import os
import json
import logging
from pathlib import Path
from typing import TypedDict, Optional, List, Dict, Any, Tuple, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import re

from ..utils.structure import get_problem_paths
from ..utils.test_runner import find_test_cases, run_tests
from ..utils.env import get_settings

logger = logging.getLogger(__name__)

class OptimalSolutionState(TypedDict):
    """State for optimal solution generation workflow."""
    problem_dir_path: str
    problem_statement: str
    bruteforce_code: str
    example_test_cases: List[Dict[str, str]]
    optimal_code: Optional[str]
    test_failures: List[Dict[str, str]]
    iteration_count: int
    time_limit: float
    human_feedback: Optional[str]
    is_refinement: bool  # Whether we're in refinement mode
    final_verdict: Optional[Literal["SUCCESS", "FAILURE"]]
    final_optimal_path: Optional[str]
    llm: any  # LLM client injected from workflow
    language: Optional[str]  # Programming language to use (C++ or Python)

def load_context_node(state: OptimalSolutionState) -> dict:
    """Loads problem statement, bruteforce solution, and example test cases."""
    logger.info("Loading context from: %s", state['problem_dir_path'])
    
    paths = get_problem_paths(state["problem_dir_path"])
    
    # Load problem statement
    if not paths.problem_statement.exists():
        raise FileNotFoundError(f"Problem statement not found at {paths.problem_statement}")
    problem_statement = paths.problem_statement.read_text(encoding="utf-8")
    logger.info("Loaded problem statement")
    
    # Get language setting and load appropriate bruteforce solution
    language = state.get("language", "C++")
    logger.info(f"Using language: {language}")
    
    bruteforce_solution_path = paths.get_bruteforce_solution_path(language)
    bruteforce_code = ""
    if bruteforce_solution_path.exists():
        bruteforce_code = bruteforce_solution_path.read_text(encoding="utf-8").strip()
        logger.info("Loaded bruteforce solution from %s (%d chars)", 
                    bruteforce_solution_path, len(bruteforce_code))
    else:
        logger.warning("No bruteforce solution found at %s, proceeding without it", 
                      bruteforce_solution_path)
    
    # Load test cases using test_runner utility
    test_cases = find_test_cases(paths.test_cases)
    logger.info("Loaded %d test cases", len(test_cases))
    
    return {
        "problem_statement": problem_statement,
        "bruteforce_code": bruteforce_code,
        "example_test_cases": test_cases
    }

def generate_optimal_node(state: OptimalSolutionState) -> dict:
    """Generates an optimal solution based on problem statement and bruteforce solution."""
    logger.info("Generating optimal solution")

    # Check if we're in refinement mode
    paths = get_problem_paths(state["problem_dir_path"])
    language = state.get("language", "C++")
    variables = {
        "problem_statement": state["problem_statement"], 
        "bruteforce_code": state["bruteforce_code"],
        "language": language
    }

    if state["is_refinement"]:
        prev_version = state.get("iteration_count", 0) - 1
        
        # Load previous optimal solution
        prev_solution_path = paths.get_optimal_path(prev_version, language)
        if not prev_solution_path.exists():
            raise FileNotFoundError(f"Previous optimal solution not found at {prev_solution_path}")
        previous_optimal = prev_solution_path.read_text(encoding="utf-8")
        logger.info("Loaded previous optimal solution v%d", prev_version)
        
        # Load previous test failures
        failures_path = paths.optimal_dir / f"optimalSolution_v{prev_version}_failures.json"
        failures = []
        if failures_path.exists():
            failures = json.loads(failures_path.read_text(encoding="utf-8"))
            logger.info("Loaded test failures from previous version %d", prev_version)
        else:
            logger.info("No previous test failures found")
        
        # Handle empty feedback string
        feedback = state["human_feedback"] or "Please improve the solution based on the test failures above."
        
        prompt_path = Path(__file__).parent.parent / "prompts/refine_optimal_solution.txt"
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code": state["bruteforce_code"],
            "previous_optimal": previous_optimal,
            "test_failures": json.dumps(failures, indent=2),
            "feedback": feedback,
            "language": language
        }
    else:
        # Use basic generation prompt
        prompt_path = Path(__file__).parent.parent / "prompts/gen_optimal_solution.txt"
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code": state["bruteforce_code"],
            "language": language
        }
    
    # Debug: Print the final rendered prompt
    messages = prompt.format_messages(**variables)
    logger.debug("Final rendered prompt:")
    logger.debug("=" * 80)
    for msg in messages:
        if isinstance(msg, HumanMessage):
            logger.debug(msg.content)
    logger.debug("=" * 80)
    
    # Generate solution
    chain = prompt | state["llm"]
    response = chain.invoke(variables)
    
    # Extract code from response based on language
    language_regex = {
        "C++": r'```(?:cpp|c\+\+)?\s*([\s\S]+?)\s*```',
        "Python": r'```(?:python|py)?\s*([\s\S]+?)\s*```'
    }
    
    pattern = language_regex.get(language, r'```(?:cpp|python|py|c\+\+)?\s*([\s\S]+?)\s*```')
    code_match = re.search(pattern, response.content)
    if not code_match:
        raise ValueError("Could not extract code from LLM response")
    
    optimal_code = code_match.group(1).strip()

    # Save solution with appropriate file extension
    iteration = state.get("iteration_count", 0)
    file_ext = "cpp" if language == "C++" else "py"
    solution_path = paths.optimal_dir / f"optimalSolution_v{iteration}.{file_ext}"
    
    # Create directory if needed
    paths.optimal_dir.mkdir(parents=True, exist_ok=True)
    solution_path.write_text(optimal_code, encoding="utf-8")
    
    # Update settings
    settings = paths.get_settings()
    settings["optimalSolutionVersion"] = iteration
    paths.update_settings(settings)
    
    logger.info("Saved solution version %d to: %s", iteration, solution_path)
    
    return {
        "optimal_code": optimal_code,
        "final_optimal_path": str(solution_path)
    }

def test_optimal_node(state: OptimalSolutionState) -> dict:
    """
    Tests the optimal solution, saves a detailed report for every run,
    and creates a separate failures-only report if any tests fail.
    The report now includes the tested code and test case path.
    """
    logger.info("Testing optimal solution")
    
    if not state["optimal_code"]:
        return {"test_failures": [{"test_name": "generation", "reason": "No optimal code generated"}], "final_verdict": "FAILURE"}
    
    paths = get_problem_paths(state["problem_dir_path"])
    
    # Run tests to get the detailed report object
    language = state.get("language", "C++")
    test_report = run_tests(
        solution_code=state["optimal_code"],
        test_cases=state["example_test_cases"],
        language=language
    )

    # Add code and test path to the main report 
    test_report["solution_code"] = state["optimal_code"]
    test_report["test_cases_path"] = str(paths.test_cases)
    
    iteration = state.get("iteration_count", 0)
    
    # Always save the full detailed report 
    full_report_path = paths.optimal_dir / f"optimalSolution_v{iteration}_report.json"
    full_report_path.write_text(json.dumps(test_report, indent=2), encoding="utf-8")
    logger.info("Full test report saved to: %s", full_report_path)

    # Check for failures based on the summary
    summary = test_report.get("summary", {})
    failures = summary.get("status") == "ERROR" or summary.get("failures", 0) > 0

    if failures:
        
        failed_cases = [res for res in test_report.get("results", []) if res["status"] != "PASSED"]
        failures_report = {
            "summary": test_report["summary"],
            "failed_tests": failed_cases,
            "solution_code": state["optimal_code"],
            "test_cases_path": str(paths.test_cases)
        }
        failures_path = paths.optimal_dir / f"optimalSolution_v{iteration}_failures.json"
        failures_path.write_text(json.dumps(failures_report, indent=2), encoding="utf-8")
        logger.info("Failures-only report saved to: %s", failures_path)
        
        # The state still only needs the list of failed cases for potential refinement
        return {**state, "test_failures": failed_cases, "final_verdict": None}
    else:
        # On success, copy the code to standard solution with appropriate extension
        standard_path = paths.get_standard_solution_path(language)
        standard_path.write_text(state["optimal_code"], encoding="utf-8")
        logger.info("Copied successful solution to: %s", standard_path)
        return {**state, "test_failures": [], "final_verdict": "SUCCESS"}