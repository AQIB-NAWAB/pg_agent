from pathlib import Path
from typing import Dict, List
import glob
import re
import logging
import tempfile
from ..pipeline.sandbox.sandbox_utils import run_test_suite

logger = logging.getLogger(__name__)

def natural_sort_key(s):
    """Key function for natural sorting of numeric filenames."""
    s = str(s)
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def find_test_cases_by_pattern(test_cases_dir: Path, pattern: str) -> List[Dict[str, str]]:
    """Find all test cases in the given directory that match the given pattern.
    
    Args:
        test_cases_dir: Path to the test cases directory
        pattern: Pattern to match
    """
    pairs = []
    in_files = sorted(test_cases_dir.glob(pattern), key=natural_sort_key)
    for in_file in in_files:
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            logger.debug("Found pair: %s -> %s", in_file.name, out_file.name)
            pairs.append((in_file, out_file))
        else:
            logger.warning("Missing output file for %s", in_file.name)
    return pairs


def find_orphaned_test_cases_by_pattern(test_cases_dir: Path, pattern: str) -> List[Dict[str, str]]:
    """Find all orphaned test cases in the given directory that match the given pattern.
    
    Args:
        test_cases_dir: Path to the test cases directory
        pattern: Pattern to match
    """
    test_cases = []
    in_files = sorted(test_cases_dir.glob(pattern), key=natural_sort_key)
    for in_file in in_files:
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            logger.info("Found orphaned: %s", in_file.name)
            test_cases.append(in_file.name)
    return test_cases


def find_test_cases(test_cases_dir: Path, small_test_cases: bool = False) -> List[Dict[str, str]]:
    """Find all test cases in the given directory.
    
    Looks for test files in the following patterns and their corresponding .out files:
    - example_*.in: Example test cases
    - test_[0-9]*.in: Standard test cases
    - [0-9]*.in: Numbered test cases
    - test_edge_*.in: Edge case tests
    
    Test cases are returned in order (examples first, then numbered tests, then edge cases).
    Only includes test cases where both .in and .out files exist.
    
    Args:
        test_cases_dir: Path to the test cases directory
        
    Returns:
        List of test case dictionaries with input, output and name fields
    """
    logger.info("Finding test cases in: %s", test_cases_dir)
    
    if not test_cases_dir.exists():
        logger.warning("Test cases directory does not exist")
        return []
        
    test_cases = []
    all_pairs = []
    
    logger.info("Looking for example test cases...")
    example_pairs = find_test_cases_by_pattern(test_cases_dir, "example_*.in")
    all_pairs.extend(example_pairs)
    
    logger.info("Looking for small test cases...")
    small_test_pairs = find_test_cases_by_pattern(test_cases_dir, "test_[0-9]*.in")
    all_pairs.extend(small_test_pairs)
   
    numbered_pairs = []
    edge_pairs = []
    if not small_test_cases:
        logger.info("Looking for numbered test cases...")
        numbered_pairs = find_test_cases_by_pattern(test_cases_dir, "[0-9]*.in")
        all_pairs.extend(numbered_pairs)
        
        logger.info("Looking for edge test cases...")
        edge_pairs = find_test_cases_by_pattern(test_cases_dir, "test_edge_*.in")
        all_pairs.extend(edge_pairs)
        
    # Add all tests in order
    for in_file, out_file in all_pairs:
        test_cases.append({
            "input": in_file.read_text(encoding="utf-8"),
            "output": out_file.read_text(encoding="utf-8").strip(),
            "name": in_file.name
        })
    
    logger.info("Found %d example(s), %d small test(s), %d numbered test(s), and %d edge test(s)", 
                len(example_pairs), len(small_test_pairs), len(numbered_pairs), len(edge_pairs))
    
    return test_cases

def find_orphaned_test_inputs(test_cases_dir: Path) -> List[str]:
    """Find all test case input files that are missing their corresponding output files.
    
    Looks for test files in the following patterns that don't have matching .out files:
    - example_*.in: Example test cases
    - test_*.in: Standard test cases
    - [0-9]+.in: Numbered test cases
    - edge_*.in: Edge case tests
    
    Test cases are returned in order (examples first, then numbered tests, then edge cases).
    
    Args:
        test_cases_dir: Path to the test cases directory
        
    Returns:
        List of file names (strings) for input files missing their output files
    """
    logger.info("Finding orphaned test inputs in: %s", test_cases_dir)
    
    if not test_cases_dir.exists():
        logger.warning("Test cases directory does not exist")
        return []
        
    orphaned_inputs = []
    
    # First collect orphaned example test cases
    logger.info("Looking for orphaned example test cases...")
    orphaned_inputs.extend(find_orphaned_test_cases_by_pattern(test_cases_dir, "example_*.in"))
            
    # Then collect all orphaned numbered test cases (both test_N.in and N.in patterns)
    logger.info("Looking for orphaned numbered test cases...")
    orphaned_inputs.extend(find_orphaned_test_cases_by_pattern(test_cases_dir, "test_[0-9]*.in"))
    orphaned_inputs.extend(find_orphaned_test_cases_by_pattern(test_cases_dir, "[0-9]*.in"))
    orphaned_inputs.extend(find_orphaned_test_cases_by_pattern(test_cases_dir, "test_edge_*.in"))
    
    logger.info("Found %d orphaned test cases", len(orphaned_inputs))
    return orphaned_inputs


def run_tests(
    solution_code: str,
    test_cases: List[Dict[str, str]],
    time_limit: float = 5.0,
    run_full_suite: bool = False,
    memory_limit: str = 512,
    cpu_limit: str = "1.5"
) -> Dict:
    """
    Uses the sandbox_utils.run_test_suite helper to execute tests and then
    parses the output files to create a detailed report.

    Args:
        solution_code: The C++ solution code to test
        test_cases: List of test cases, each with 'input', 'output' and 'name' fields
        time_limit: Time limit in seconds for each test case
        run_full_suite: If True, run all tests even after a failure
        memory_limit: Memory limit in MB
        cpu_limit: CPU limit for Docker container

    Returns:
        Dict containing:
        - summary: Overall test results including status and counts
        - results: List of detailed results for each test case
            Each result includes:
            - test_name: Name of the test case
            - status: One of:
                - "PASSED"
                - "WRONG_ANSWER"
                - "TIME_LIMIT_EXCEEDED"
                - "MEMORY_LIMIT_EXCEEDED"
                - "SIGSEGV"
                - "SIGABRT"
                - "RTE(Signal X)"
                - "NZEC" (Non-Zero Exit Code)
            - execution_time_ms: Execution time in milliseconds
            - memory_usage_kb: Memory usage in kilobytes
            - actual_output: Present only for WRONG_ANSWER status
    """
    if not test_cases:
        return {"summary": {"status": "SUCCESS", "passed": 0, "failed": 0, "total_run": 0, "total_available": 0}, "results": []}

    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        
        (work_dir / "solution.cpp").write_text(solution_code, encoding="utf-8")
        for tc in test_cases:
            (work_dir / tc["name"]).write_text(tc["input"], encoding="utf-8")
        
        try:
            # Call the existing helper function to run the Docker container.
            # This function is responsible for creating the .out and .prof files.
            stdout, stderr = run_test_suite(
                solution_path=str(work_dir / "solution.cpp"),
                test_cases_dir=work_dir,
                time_limit=time_limit,
                memory_limit=memory_limit,
                run_full_suite=run_full_suite
            )
        except Exception as e:
            # If run_test_suite throws an exception, it's likely a Docker error.
            error_str = str(e).lower()
            logger.error(f"Error: {error_str}")
            return {"summary": {"status": "ERROR", "message": "Docker execution failed."}, "details": str(e), "results": []}
        
        if "COMPILATION_FAILED" in stdout:
            # Read the compilation error from compilation_error.log and include it in the results
            comp_err_log = work_dir / "compilation_error.log"
            details = ""
            if comp_err_log.exists():
                details = comp_err_log.read_text(encoding="utf-8")

            return {
                "summary": {"status": "COMPILATION_ERROR", "passed": 0, "failed": len(test_cases), "total_run": 0, "total_available": len(test_cases)},
                "results": [{"status": "COMPILATION_ERROR", "details": details}]
            }

        # --- After execution, parse the results from the temporary directory ---
        logger.info("Parsing results from temporary directory...")
        detailed_results = []
        tc_map = {tc['name']: tc for tc in test_cases}
        
        for test_case in test_cases:
            test_name = test_case["name"]
            out_file = work_dir / test_name.replace(".in", ".out")
            prof_file = work_dir / test_name.replace(".in", ".prof")

            if not prof_file.exists() and not out_file.exists():
                continue

            time_sec, mem_kb, exit_code = 0.0, 0, 1 # Default to runtime error
            status = "RUNTIME_ERROR"

            if prof_file.exists():
                try:
                    prof_file_content = prof_file.read_text()
                    time_sec = float(re.search(r"TIME:([\d.]+)", prof_file_content).group(1))
                    mem_kb = int(re.search(r"MEM:(\d+)", prof_file_content).group(1))
                    exit_code = int(re.search(r"STATUS:(\d+)", prof_file_content).group(1))
                except (AttributeError, ValueError):
                    logger.warning(f"Could not parse stats from {prof_file.name}")
            
            if not out_file.exists():
                status = "RUNTIME_ERROR"
            else:
                actual_stdout = out_file.read_text(encoding="utf-8").strip()
                expected_output = tc_map[test_name]["output"].strip()
                
                # Convert memory limit to KB
                memory_limit_kb = memory_limit * 1024
                
                if mem_kb > memory_limit_kb:
                    status = "MEMORY_LIMIT_EXCEEDED"
                elif actual_stdout == "TIMEOUT":
                    status = "TIME_LIMIT_EXCEEDED"
                elif actual_stdout == "RUNTIME_ERROR":
                     if exit_code > 128:
                        signal = exit_code - 128
                        if signal == 11: status = "SIGSEGV"
                        elif signal == 6: status = "SIGABRT"
                        else: status = f"RTE(Signal {signal})"
                     else:
                        status = "NZEC"
                elif actual_stdout == expected_output:
                    status = "PASSED"
                else:
                    status = "WRONG_ANSWER"
            
            result_item = {
                "test_name": test_name, "status": status,
                "execution_time_ms": time_sec * 1000,
                "memory_usage_kb": mem_kb
            }
            if status == "WRONG_ANSWER":
                result_item["actual_output"] = actual_stdout
            detailed_results.append(result_item)

            if not run_full_suite and status != "PASSED":
                break

    total_run = len(detailed_results)
    passed_count = sum(1 for r in detailed_results if r['status'] == 'PASSED')
    failed_count = total_run - passed_count
    
    if failed_count > 0:
        final_status = "FAILURE"
    else:
        final_status = "SUCCESS"

    summary = {"status": final_status, "passed": passed_count, "failed": failed_count, "total_run": total_run, "total_available": len(test_cases)}

    return {"summary": summary, "results": detailed_results}