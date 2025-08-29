import os
import json
import shutil
import logging
from pathlib import Path
import tempfile
from typing import TypedDict, Optional, List, Literal

from ..pipeline.sandbox.sandbox_utils import (
    run_generator_script,
    run_validation_suite,
    run_test_suite
)
from ..utils.structure import get_problem_paths
from ..utils.test_runner import find_orphaned_test_inputs

logger = logging.getLogger(__name__)

class TestSuiteState(TypedDict):
    """
    Represents the state for the Test Suite Generation workflow.
    """
    # --- Initial inputs ---
    problem_dir_path: str
    bruteforce_time_limit: float
    generation_mode: Literal["validator", "outputs"]  # Mode of operation
    use_bruteforce: bool  # Whether to use bruteforce solution
    use_optimal: bool  # Whether to use optimal solution
    solutions_to_process: List[dict]  # List of solutions to process with their configs

    # --- Data loaded from files ---
    solution_path: str  # Path to either bruteforce or optimal solution (legacy, kept for compatibility)
    validator_path: str
    
    # --- Internal state ---
    run_dir_path: str  # Path to temporary directory for generated files
    valid_test_inputs: Optional[List[str]]  # Paths to valid test inputs
    invalid_tests: Optional[List[dict]]  # Details about invalid test cases
    current_solution_index: int  # Index of current solution being processed


def load_scripts_node(state: TestSuiteState) -> dict:
    """Loads the required C++ scripts from the problem root directory."""
    print(f"--- Loading scripts from: {state['problem_dir_path']} ---")
    paths = get_problem_paths(state['problem_dir_path'])

    # Create temporary run directory
    run_dir = Path(tempfile.gettempdir()) / f"pg_agent_run_{os.urandom(4).hex()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created temporary run directory: {run_dir}")

    # Load scripts based on mode
    result = {
        "run_dir_path": str(run_dir),
        "invalid_tests": [],
        "current_solution_index": 0
    }

    def check_script(path: Path) -> str:
        """Helper to check and get script path."""
        if not path.exists():
            raise FileNotFoundError(f"Script file not found: {path}")
        return str(path)

    # Load validator if in validator mode
    if state["generation_mode"] == "validator":
        result["validator_path"] = check_script(paths.validator)
    
    # Load solution if in outputs mode
    if state["generation_mode"] == "outputs":
        solutions_to_process = []
        
        # Add bruteforce solution if requested
        if state.get("use_bruteforce", False):
            try:
                bruteforce_path = check_script(paths.bruteforce_solution)
                solutions_to_process.append({
                    "type": "bruteforce",
                    "path": bruteforce_path,
                    "time_limit": state["bruteforce_time_limit"],
                    "memory_limit": 512
                })
                logger.info("Added bruteforce solution (solution_bf.cpp) for output generation")
            except FileNotFoundError:
                logger.warning("Bruteforce solution (solution_bf.cpp) not found, skipping")
        
        # Add optimal solution if requested
        if state.get("use_optimal", False):
            try:
                optimal_path = check_script(paths.standard_solution)
                solutions_to_process.append({
                    "type": "optimal",
                    "path": optimal_path,
                    "time_limit": state["bruteforce_time_limit"],
                    "memory_limit": 512
                })
                logger.info("Added optimal solution (standard.cpp) for output generation")
            except FileNotFoundError:
                logger.warning("Optimal solution (standard.cpp) not found, skipping")
        
        if not solutions_to_process:
            raise FileNotFoundError("No valid solutions found for output generation")
        
        result["solutions_to_process"] = solutions_to_process
        
        # Set initial solution path for compatibility
        if solutions_to_process:
            result["solution_path"] = solutions_to_process[0]["path"]

    return result

def validate_inputs_node(state: TestSuiteState) -> dict:
    """Runs the validator script against all test cases and gets a detailed report."""
    if state["generation_mode"] != "validator":
        logger.info("Skipping validation (not in validator mode)")
        return {}
        
    print("--- Validating all test input files ---")
    paths = get_problem_paths(state['problem_dir_path'])
    
    all_inputs = list(paths.test_cases.glob("*.in"))

    #debugging output
    print(f"Found {len(all_inputs)} input files in {paths.test_cases}")
    
    if not all_inputs:
        logger.warning("No input files found to validate.")
        return {"validation_report": {"summary": {"status": "SUCCESS", "message": "No input files found."}}}

    # Call the new detailed validation runner
    validation_report = run_validation_suite(state['validator_path'], all_inputs)
    
    # Log invalid test cases from the new report structure
    invalid_tests = [res for res in validation_report.get("results", []) if res["status"] == "INVALID"]
    for invalid in invalid_tests:
        logger.warning(f"Invalid test case file '{invalid['test_name']}'. Reason: {invalid.get('reason', 'N/A')}")

    print(f"Validation complete:")
    print(f"- Valid tests: {validation_report.get('summary', {}).get('valid', 0)}")
    print(f"- Invalid tests: {validation_report.get('summary', {}).get('invalid', 0)}")
    
    return {"validation_report": validation_report}

def generate_outputs_node(state: TestSuiteState) -> dict:
    """Generates outputs for test cases using all available solutions."""
    if state["generation_mode"] != "outputs":
        logger.info("Skipping output generation (not in outputs mode)")
        return {}
    
    solutions_to_process = state.get("solutions_to_process", [])
    if not solutions_to_process:
        logger.warning("No solutions to process for output generation")
        return {"valid_test_inputs": [], "invalid_tests": state.get("invalid_tests", [])}
    
    print(f"--- Generating outputs for test cases using {len(solutions_to_process)} solution(s) ---")
    
    invalid_tests = []
    all_valid_tests = []
    
    # Get problem paths once
    paths = get_problem_paths(state['problem_dir_path'])
    
    # Process each solution
    for i, solution_config in enumerate(solutions_to_process):
        solution_type = solution_config["type"]
        solution_path = solution_config["path"]
        time_limit = solution_config["time_limit"]
        memory_limit = solution_config["memory_limit"]
        
        print(f"\n--- Processing {solution_type} solution ({i+1}/{len(solutions_to_process)}) ---")
        print(f"Solution: {solution_path}")
        print(f"Time limit: {time_limit}s, Memory limit: {memory_limit}MB")
        
        # Find test cases that still need outputs generated (re-fetch after each solution)
        orphaned_tests = find_orphaned_test_inputs(paths.test_cases)
        
        if not orphaned_tests:
            logger.info(f"No more test cases need outputs after {solution_type} solution. Skipping remaining solutions.")
            break
        
        print(f"Found {len(orphaned_tests)} test cases that still need outputs")
        
        # Create a temporary directory for this solution
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            
            # Copy all remaining orphaned test inputs to temp directory
            for test_name in orphaned_tests:
                full_path = paths.test_cases / test_name
                shutil.copy(full_path, temp_dir)
                
            # Run all tests with this solution
            run_test_suite(
                solution_path=solution_path,
                test_cases_dir=temp_dir,
                time_limit=time_limit,
                memory_limit=memory_limit,
                run_full_suite=True
            )
            
            # Process results for this solution
            solution_valid_tests = []
            invalid_tests = []
            for test_name in orphaned_tests:
                full_path = paths.test_cases / test_name
                out_file_in_temp = temp_dir / test_name.replace(".in", ".out")
                
                if out_file_in_temp.exists():
                    content = out_file_in_temp.read_text(encoding="utf-8").strip()
                    if content == "TIMEOUT":
                        logger.warning(f"{solution_type} solution timed out on '{test_name}'. Discarding.")
                        invalid_tests.append({
                            "file": test_name,
                            "reason": f"{solution_type} solution Timed Out (limit: {time_limit}s)"
                        })
                    else:
                        # Copy output back to original location
                        shutil.copy(out_file_in_temp, full_path.with_suffix(".out"))
                        solution_valid_tests.append(str(full_path))
                        logger.info(f"{solution_type} solution generated output for '{test_name}'")
                else:
                    logger.warning(f"No output file for '{test_name}' from {solution_type} solution. Assuming runtime error.")
                    invalid_tests.append({
                        "file": test_name,
                        "reason": f"{solution_type} solution Runtime Error"
                    })
            
            print(f"{solution_type} solution finished: {len(solution_valid_tests)} outputs generated")
            all_valid_tests.extend(solution_valid_tests)
    
    # Remove duplicates from all_valid_tests
    all_valid_tests = list(set(all_valid_tests))
    
    print(f"\n--- All solutions completed ---")
    print(f"Total outputs generated: {len(all_valid_tests)}")
    print(f"Total invalid tests: {len(invalid_tests)}")
    
    return {
        "valid_test_inputs": all_valid_tests,
        "invalid_tests": invalid_tests
    }

def finalize_node(state: TestSuiteState) -> dict:
    """Cleanup and save final reports."""
    paths = get_problem_paths(state['problem_dir_path'])
    
    # Save detailed validation report
    if state.get("validation_report"):
        report_path = paths.automation_dir / "validation_report.json"
        report_path.write_text(
            json.dumps(state["validation_report"], indent=2),
            encoding="utf-8"
        )
        logger.info(f"Detailed validation report saved to {report_path}")

    # Save test case log for output generation failures
    invalid_tests = state.get("invalid_tests", [])
    if invalid_tests and state["generation_mode"] == "outputs":
        log_path = paths.test_cases / "failed_testcases.json"
        log_path.write_text(
            json.dumps(invalid_tests, indent=2),
            encoding="utf-8"
        )
    
    # Cleanup temporary directory
    run_dir = Path(state['run_dir_path'])
    if run_dir.exists():
        shutil.rmtree(run_dir)
        logger.info("Cleaned up temporary directory")
    return {}