import os
import json
import shutil
import logging
from pathlib import Path
import tempfile
from typing import TypedDict, Optional, List

from ..pipeline.sandbox.sandbox_utils import (
    run_generator_script,
    run_validation_suite,
    run_test_suite
)

logger = logging.getLogger(__name__)

class TestSuiteState(TypedDict):
    """
    Represents the state for the Test Suite Generation workflow.
    """
    # --- Initial inputs ---
    problem_dir_path: str
    bruteforce_time_limit: float
    skip_small_tests: bool
    skip_large_tests: bool

    # --- Data loaded from files ---
    bruteforce_path: str
    small_test_gen_path: str
    stress_test_gen_path: str
    validator_path: str
    
    # --- Internal state ---
    run_dir_path: str  # Path to temporary directory for generated files
    valid_small_tests: Optional[List[str]]  # Paths to valid small test inputs
    valid_large_tests: Optional[List[str]]  # Paths to valid large test inputs
    invalid_tests: Optional[List[dict]]  # Details about invalid test cases

    # --- Final output ---
    final_verdict: Optional[str]

def load_scripts_node(state: TestSuiteState) -> dict:
    """Loads the latest versions of all required C++ scripts from the automation directory."""
    print(f"--- Loading scripts from: {state['problem_dir_path']}/automation ---")
    problem_dir = Path(state['problem_dir_path'])
    automation_dir = problem_dir / "automation"
    settings_path = automation_dir / "automation_settings.json"

    if not settings_path.exists():
        raise FileNotFoundError("automation_settings.json not found. Please run previous workflows first.")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    
    def get_path(key: str, folder: str) -> str:
        """Helper to get the latest version of a script."""
        version = settings.get(key, -1)
        if version == -1:
            raise FileNotFoundError(f"'{key}' not found in settings. Please run required workflows.")
        prefix = key.replace("Version", "")
        path = automation_dir / folder / f"{prefix}_v{version}.cpp"
        if not path.exists():
            raise FileNotFoundError(f"Script file not found: {path}")
        return str(path)

    # Create temporary run directory
    run_dir = Path(tempfile.gettempdir()) / f"pg_agent_run_{os.urandom(4).hex()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created temporary run directory: {run_dir}")

    return {
        "bruteforce_path": get_path("bruteforceSolutionVersion", "bruteForceSol"),
        "small_test_gen_path": get_path("smallTestcaseGeneratorVersion", "testcaseGenScript"),
        "stress_test_gen_path": get_path("stressTestcaseGeneratorVersion", "testcaseGenScript"),
        "validator_path": get_path("testcaseValidatorVersion", "testcaseGenScript"),
        "run_dir_path": str(run_dir),
        "invalid_tests": []
    }

def run_generators_node(state: TestSuiteState) -> dict:
    """Runs the test case generator scripts in the sandbox."""
    print("--- Running test case generator scripts ---")
    run_dir = Path(state['run_dir_path'])
    
    if not state["skip_small_tests"]:
        print("  Generating small test cases...")
        small_tests_dir = run_dir / "small"
        small_tests_dir.mkdir()
        run_generator_script(state['small_test_gen_path'], small_tests_dir)
    else:
        logger.info("Skipping small test case generation")
    
    if not state["skip_large_tests"]:
        print("  Generating stress test cases...")
        large_tests_dir = run_dir / "large"
        large_tests_dir.mkdir()
        run_generator_script(state['stress_test_gen_path'], large_tests_dir)
    else:
        logger.info("Skipping large test case generation")
    
    print("Finished generating test case inputs.")
    return {}

def validate_inputs_node(state: TestSuiteState) -> dict:
    """Runs the validator script against all generated and example test cases."""
    print("--- Validating all generated input files ---")
    run_dir = Path(state['run_dir_path'])
    problem_dir = Path(state['problem_dir_path'])
    
    # Collect all input files to validate
    all_inputs = []
    if not state["skip_small_tests"]:
        all_inputs.extend(list((run_dir / "small").glob("*.in")))
    if not state["skip_large_tests"]:
        all_inputs.extend(list((run_dir / "large").glob("*.in")))
    all_inputs.extend(list((problem_dir / "test_cases").glob("example_*.in")))

    if not all_inputs:
        logger.warning("No input files found to validate.")
        return {"valid_small_tests": [], "valid_large_tests": [], "invalid_tests": []}

    valid_paths, invalid_dicts = run_validation_suite(state['validator_path'], all_inputs)

    # Sort valid paths into small and large tests
    valid_small_tests = []
    valid_large_tests = []
    for p in valid_paths:
        if "small" in str(p.parent) or "example" in p.name:
            valid_small_tests.append(str(p))
        elif "large" in str(p.parent):
            valid_large_tests.append(str(p))
            
    # Log invalid test cases
    for invalid in invalid_dicts:
        logger.warning(f"Invalid test case file '{invalid['file']}'. Reason: {invalid['reason']}")

    print(f"Validation complete:")
    print(f"- Valid small tests: {len(valid_small_tests)}")
    print(f"- Valid large tests: {len(valid_large_tests)}")
    print(f"- Invalid tests: {len(invalid_dicts)}")
    
    return {
        "valid_small_tests": valid_small_tests,
        "valid_large_tests": valid_large_tests,
        "invalid_tests": invalid_dicts
    }

def run_bruteforce_on_small_tests_node(state: TestSuiteState) -> dict:
    """Runs the bruteforce solution on all valid small tests efficiently."""
    if state["skip_small_tests"]:
        logger.info("Skipping bruteforce solution run (small tests generation was skipped)")
        return {}
        
    print("--- Generating outputs for small test cases using bruteforce ---")
    
    invalid_tests = state.get("invalid_tests", [])
    valid_small_test_paths = [Path(p) for p in state.get('valid_small_tests', [])]

    if not valid_small_test_paths:
        logger.warning("No valid small tests to run.")
        return {"valid_small_tests": [], "invalid_tests": invalid_tests}

    # Create a single temporary directory for batch processing
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        
        # Copy all valid small test inputs to temp directory
        for in_file_path in valid_small_test_paths:
            shutil.copy(in_file_path, temp_dir)
            
        # Run all tests in one container
        run_test_suite(
            solution_path=state['bruteforce_path'],
            test_cases_dir=temp_dir,
            time_limit=state['bruteforce_time_limit']
        )
        
        # Process results
        final_valid_small_tests = []
        for in_file_path in valid_small_test_paths:
            out_file_in_temp = temp_dir / in_file_path.name.replace(".in", ".out")
            
            if out_file_in_temp.exists():
                content = out_file_in_temp.read_text(encoding="utf-8").strip()
                if content == "TIMEOUT":
                    logger.warning(f"Bruteforce timed out on '{in_file_path.name}'. Discarding.")
                    invalid_tests.append({
                        "file": in_file_path.name,
                        "reason": f"Bruteforce Timed Out (limit: {state['bruteforce_time_limit']}s)"
                    })
                else:
                    # Copy output back to original location
                    shutil.copy(out_file_in_temp, in_file_path.with_suffix(".out"))
                    final_valid_small_tests.append(str(in_file_path))
            else:
                logger.warning(f"No output file for '{in_file_path.name}'. Assuming runtime error.")
                invalid_tests.append({
                    "file": in_file_path.name,
                    "reason": "Bruteforce Runtime Error"
                })

    print(f"Finished generating outputs for {len(final_valid_small_tests)} valid small tests.")
    return {
        "valid_small_tests": final_valid_small_tests,
        "invalid_tests": invalid_tests
    }

def save_results_node(state: TestSuiteState) -> dict:
    """Saves the final, validated test suite to the automation directory."""
    print("--- Saving final test suite to automation folder ---")
    run_dir = Path(state['run_dir_path'])
    automation_test_cases_dir = Path(state['problem_dir_path']) / "automation" / "testcases"
    
    # Create directory structure
    for subdir in ["small", "large", "example"]:
        (automation_test_cases_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Copy valid small tests and examples
    for test_path_str in state.get('valid_small_tests', []):
        test_path = Path(test_path_str)
        dest_dir = automation_test_cases_dir / ("example" if "example" in test_path.name else "small")
        
        if test_path.exists():
            shutil.copy(test_path, dest_dir / test_path.name)
            out_path = test_path.with_suffix(".out")
            if out_path.exists():
                shutil.copy(out_path, dest_dir / out_path.name)

    # Copy valid large tests (input only)
    for test_path_str in state.get('valid_large_tests', []):
        test_path = Path(test_path_str)
        if test_path.exists():
            shutil.copy(test_path, automation_test_cases_dir / "large" / test_path.name)

    # Save invalid test case log
    invalid_log_path = automation_test_cases_dir / "invalid_testcases.json"
    invalid_log_path.write_text(
        json.dumps(state.get("invalid_tests", []), indent=2),
        encoding="utf-8"
    )
            
    # Cleanup
    if run_dir.exists():
        shutil.rmtree(run_dir)
        logger.info("Cleaned up temporary directory")
        
    print(f"Final test suite saved to {automation_test_cases_dir}")
    return {"final_verdict": "SUCCESS"} 