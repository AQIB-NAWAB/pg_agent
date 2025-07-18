import os
import json
import logging
from pathlib import Path
from typing import TypedDict, Optional, List, Dict, Any, Tuple, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import re

from ..utils.parsing import parse_test_cases
from ..pipeline.sandbox.sandbox_utils import run_single_test

logger = logging.getLogger(__name__)

class TestFailure(TypedDict):
    test_name: str
    input: str
    expected: str
    actual: str
    reason: str

class OptimalSolutionState(TypedDict):
    """State for optimal solution generation workflow."""
    problem_dir_path: str
    problem_statement: str
    bruteforce_code: str
    example_test_cases: List[Tuple[str, str]]
    optimal_code: Optional[str]
    test_failures: List[TestFailure]
    iteration_count: int
    max_iterations: int
    time_limit: float
    human_feedback: Optional[str]
    final_verdict: Optional[Literal["SUCCESS", "FAILURE"]]
    final_optimal_path: Optional[str]

def get_llm_client():
    """Creates an OpenAI client, reading the key from the environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o4-mini", api_key=api_key)

def load_context(state: OptimalSolutionState) -> dict:
    """Loads problem statement, bruteforce solution, and example test cases."""
    print(f"--- Loading context from: {state['problem_dir_path']} ---")
    
    from ..utils.structure import get_problem_paths
    paths = get_problem_paths(state["problem_dir_path"])
    
    # Load problem statement
    if not paths.problem_statement.exists():
        raise FileNotFoundError(f"Problem statement not found at {paths.problem_statement}")
    problem_statement = paths.problem_statement.read_text(encoding="utf-8")
    print("Loaded problem statement")
    
    # Load bruteforce solution
    settings = paths.get_settings()
    bf_version = settings.get("bruteforceSolutionVersion", -1)
    
    if bf_version == -1:
        raise FileNotFoundError("Bruteforce solution not found. Please run bruteforce generator first.")
        
    bruteforce_path = paths.get_bruteforce_path(bf_version)
    bruteforce_code = bruteforce_path.read_text(encoding="utf-8")
    print("Loaded bruteforce solution")
    
    # Load example test cases
    test_cases = []
    if paths.test_cases.exists():
        for i in range(1, 100):  # Look for example_1.in, example_2.in, etc.
            input_file = paths.test_cases / f"example_{i}.in"
            output_file = paths.test_cases / f"example_{i}.out"
            if not input_file.exists() or not output_file.exists():
                break
            test_cases.append((
                input_file.read_text(encoding="utf-8").strip(),
                output_file.read_text(encoding="utf-8").strip()
            ))
    print(f"Loaded {len(test_cases)} example test cases")
    
    return {
        "problem_statement": problem_statement,
        "bruteforce_code": bruteforce_code,
        "example_test_cases": test_cases
    }

def generate_optimal(state: OptimalSolutionState) -> dict:
    """Generates an optimal solution based on problem statement and bruteforce solution."""
    print("--- Generating optimal solution ---")
    
    # If there's feedback, use refinement prompt
    if state["human_feedback"]:
        prompt_path = Path(__file__).parent.parent / "prompts/refine_optimal_solution.txt"
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code": state["bruteforce_code"],
            "example_test_cases": "\n".join(
                f"Input:\n{input}\nOutput:\n{output}\n"
                for input, output in state["example_test_cases"]
            ),
            "feedback": state["human_feedback"]
        }
    else:
        # Use basic generation prompt
        prompt_path = Path(__file__).parent.parent / "prompts/gen_optimal_solution.txt"
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code": state["bruteforce_code"],
            "example_test_cases": "\n".join(
                f"Input:\n{input}\nOutput:\n{output}\n"
                for input, output in state["example_test_cases"]
            )
        }
    
    # Generate solution
    chain = prompt | get_llm_client()
    response = chain.invoke(variables)
    
    # Extract code from response
    code_match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response.content)
    if not code_match:
        raise ValueError("Could not extract code from LLM response")
    
    optimal_code = code_match.group(1).strip()
    print("Generated optimal solution")
    
    return {"optimal_code": optimal_code}

def test_optimal(state: OptimalSolutionState) -> dict:
    """Tests the optimal solution against example cases and stress tests."""
    print("--- Testing optimal solution ---")
    
    if not state["optimal_code"]:
        return {
            "test_failures": [{"test_name": "generation", "reason": "No optimal code generated"}],
            "final_verdict": "FAILURE"
        }
    
    test_failures = []
    
    # Test example cases first
    print("\nRunning example test cases:")
    for i, (input_data, expected_output) in enumerate(state["example_test_cases"], 1):
        print(f"\nTest case {i}:")
        print(f"Input:\n{input_data}")
        print(f"Expected:\n{expected_output}")
        
        success, actual_output = run_single_test(state["optimal_code"], input_data)
        actual_output = actual_output.strip() if success else actual_output
        
        print(f"Status: {'SUCCESS' if success and actual_output == expected_output else 'FAILED'}")
        if not success or actual_output != expected_output:
            reason = "Runtime Error" if not success else "Wrong Answer"
            print(f"Actual output:\n{actual_output}")
            test_failures.append({
                "test_name": f"example_{i}",
                "input": input_data,
                "expected": expected_output,
                "actual": actual_output,
                "reason": reason
            })
    
    # Run stress tests if available
    from ..utils.structure import get_problem_paths
    paths = get_problem_paths(state["problem_dir_path"])
    stress_dir = paths.automation / "testcases" / "stress"
    
    if stress_dir.exists():
        print("\nRunning stress test cases:")
        for test_file in stress_dir.glob("*.in"):
            input_data = test_file.read_text(encoding="utf-8")
            output_file = test_file.with_suffix(".out")
            
            if not output_file.exists():
                continue
                
            print(f"\nTest case {test_file.stem}:")
            expected_output = output_file.read_text(encoding="utf-8").strip()
            success, actual_output = run_single_test(state["optimal_code"], input_data)
            actual_output = actual_output.strip() if success else actual_output
            
            print(f"Status: {'SUCCESS' if success and actual_output == expected_output else 'FAILED'}")
            if not success or actual_output != expected_output:
                reason = "Runtime Error" if not success else "Wrong Answer"
                print(f"Input:\n{input_data}")
                print(f"Expected:\n{expected_output}")
                print(f"Actual:\n{actual_output}")
                test_failures.append({
                    "test_name": test_file.stem,
                    "input": input_data,
                    "expected": expected_output,
                    "actual": actual_output,
                    "reason": reason
                })
    
    if test_failures:
        print(f"\nTest Summary: {len(test_failures)} test(s) failed")
        return {
            "test_failures": test_failures
        }
    
    print("\nTest Summary: All tests passed!")
    return {
        "test_failures": [],
        "final_verdict": "SUCCESS"
    }

def should_fix(state: OptimalSolutionState) -> str:
    """Determines whether to fix, save, or end based on test results and iteration count."""
    if not state["test_failures"]:
        return "save"
        
    if state["iteration_count"] >= state["max_iterations"]:
        return "end_failure"
        
    return "fix"

def fix_optimal(state: OptimalSolutionState) -> dict:
    """Fixes the optimal solution based on test failures."""
    print("--- Fixing optimal solution ---")
    
    # Load the fix prompt
    prompt_path = Path(__file__).parent.parent / "prompts/fix_optimal_solution.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    
    # Prepare failure summary
    failure_summary = "\n".join(
        f"Test {f['test_name']}:\n"
        f"Input:\n{f['input']}\n"
        f"Expected:\n{f['expected']}\n"
        f"Got:\n{f['actual']}\n"
        f"Reason: {f['reason']}"
        for f in state["test_failures"][:3]  # Limit to first 3 failures
    )
    
    # Generate fixed solution
    chain = prompt | get_llm_client()
    response = chain.invoke({
        "problem_statement": state["problem_statement"],
        "current_code": state["optimal_code"],
        "test_failures": failure_summary
    })
    
    # Extract code from response
    code_match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response.content)
    if not code_match:
        raise ValueError("Could not extract code from LLM response")
    
    optimal_code = code_match.group(1).strip()
    print(f"Fixed solution (iteration {state['iteration_count'] + 1})")
    
    return {
        "optimal_code": optimal_code,
        "iteration_count": state["iteration_count"] + 1
    }

def save_solution(state: OptimalSolutionState) -> dict:
    """Saves the successful optimal solution."""
    print("--- Saving optimal solution ---")
    
    from ..utils.structure import get_problem_paths
    paths = get_problem_paths(state["problem_dir_path"])
    
    # Load settings
    settings = paths.get_settings()
    current_version = settings.get("optimalSolutionVersion", -1)
    new_version = current_version + 1
    
    # Save the solution in automation directory
    paths.optimal_dir.mkdir(exist_ok=True)
    optimal_path = paths.get_optimal_path(new_version)
    optimal_path.write_text(state["optimal_code"], encoding="utf-8")
    
    # Update settings
    settings["optimalSolutionVersion"] = new_version
    paths.update_settings(settings)
    
    print(f"Saved optimal solution version {new_version}")
    
    # Copy to standard.cpp if tests passed
    if not state["test_failures"]:
        print("Tests passed - copying solution to standard.cpp")
        paths.standard_solution.write_text(state["optimal_code"], encoding="utf-8")
        print(f"Solution copied to: {paths.standard_solution}")
    
    return {
        "final_optimal_path": str(optimal_path),
        "final_verdict": "SUCCESS"
    } 