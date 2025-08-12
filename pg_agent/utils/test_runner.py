from pathlib import Path
from typing import Dict, List, Tuple
import re
import logging
import tempfile

from ..pipeline.sandbox.sandbox_utils import run_test_suite

logger = logging.getLogger(__name__)

def find_test_cases(test_cases_dir: Path, small_test_cases: bool = False) -> List[Dict[str, str]]:
    """Find all test cases in the given directory.
    
    Looks for test files in the following patterns and their corresponding .out files:
    - example_*.in: Example test cases
    - test_*.in: Standard test cases
    - [0-9]+.in: Numbered test cases
    - edge_*.in: Edge case tests
    
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
    
    # First collect example test cases
    logger.info("Looking for example test cases...")
    example_pairs = []
    for in_file in test_cases_dir.glob("example_*.in"):
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            logger.debug("Found example pair: %s -> %s", in_file.name, out_file.name)
            example_pairs.append((in_file, out_file))
        else:
            logger.warning("Missing output file for %s", in_file.name)
    
    # Add examples in sorted order
    for in_file, out_file in sorted(example_pairs):
        test_cases.append({
            "input": in_file.read_text(encoding="utf-8"),
            "output": out_file.read_text(encoding="utf-8").strip(),
            "name": in_file.name
        })
         
    # Then collect all numbered test cases (both test_N.in and N.in patterns)
    logger.info("Looking for numbered test cases...")
    numbered_pairs = []
    
    # Handle test_N.in pattern
    for in_file in test_cases_dir.glob("test_*.in"):
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            match = re.search(r'test_(\d+)\.in', in_file.name)
            if match:
                test_num = int(match.group(1))
                logger.debug("Found test pair #%d: %s -> %s", test_num, in_file.name, out_file.name)
                numbered_pairs.append((test_num, in_file, out_file))
                

    if small_test_cases:
        # Add numbered tests in order
        for _, in_file, out_file in sorted(numbered_pairs):
            test_cases.append({
                "input": in_file.read_text(encoding="utf-8"),
                "output": out_file.read_text(encoding="utf-8").strip(),
                "name": in_file.name
            })
        logger.info("Found %d example(s) and %d numbered test(s)", len(example_pairs), len(numbered_pairs))
        return test_cases
    
    # Handle N.in pattern
    for in_file in test_cases_dir.glob("[0-9]*.in"):
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            match = re.search(r'(\d+)\.in', in_file.name)
            if match:
                test_num = int(match.group(1))
                logger.debug("Found numbered pair #%d: %s -> %s", test_num, in_file.name, out_file.name)
                numbered_pairs.append((test_num, in_file, out_file))
    
    # Add numbered tests in order
    for _, in_file, out_file in sorted(numbered_pairs):
        test_cases.append({
            "input": in_file.read_text(encoding="utf-8"),
            "output": out_file.read_text(encoding="utf-8").strip(),
            "name": in_file.name
        })
    
    # Finally collect edge test cases
    logger.info("Looking for edge test cases...")
    edge_pairs = []
    for in_file in test_cases_dir.glob("edge_*.in"):
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            match = re.search(r'edge_(\d+)\.in', in_file.name)
            test_num = int(match.group(1)) if match else 0
            logger.debug("Found edge case pair: %s -> %s", in_file.name, out_file.name)
            edge_pairs.append((test_num, in_file, out_file))
    
    # Add edge tests in order
    for _, in_file, out_file in sorted(edge_pairs):
        test_cases.append({
            "input": in_file.read_text(encoding="utf-8"),
            "output": out_file.read_text(encoding="utf-8").strip(),
            "name": in_file.name
        })
    
    logger.info("Found %d example(s), %d numbered test(s), and %d edge test(s)", 
                len(example_pairs), len(numbered_pairs), len(edge_pairs))
    
    logger.info("Found %d example(s)", len(test_cases))
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
    for in_file in test_cases_dir.glob("example_*.in"):
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            logger.debug("Found orphaned example: %s", in_file.name)
            orphaned_inputs.append(in_file.name)
            
    # Then collect all orphaned numbered test cases (both test_N.in and N.in patterns)
    logger.info("Looking for orphaned numbered test cases...")
    numbered_orphans = []
    
    # Handle test_N.in pattern
    for in_file in test_cases_dir.glob("test_*.in"):
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            match = re.search(r'test_(\d+)\.in', in_file.name)
            if match:
                test_num = int(match.group(1))
                logger.debug("Found orphaned test #%d: %s", test_num, in_file.name)
                numbered_orphans.append((test_num, in_file.name))
    
    # Handle N.in pattern
    for in_file in test_cases_dir.glob("[0-9]*.in"):
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            match = re.search(r'(\d+)\.in', in_file.name)
            if match:
                test_num = int(match.group(1))
                logger.debug("Found orphaned numbered test #%d: %s", test_num, in_file.name)
                numbered_orphans.append((test_num, in_file.name))
    
    # Add numbered orphans in order
    for _, name in sorted(numbered_orphans):
        orphaned_inputs.append(name)
    
    # Finally collect orphaned edge test cases
    logger.info("Looking for orphaned edge test cases...")
    edge_orphans = []
    for in_file in test_cases_dir.glob("edge_*.in"):
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            match = re.search(r'edge_(\d+)\.in', in_file.name)
            test_num = int(match.group(1)) if match else 0
            logger.debug("Found orphaned edge case: %s", in_file.name)
            edge_orphans.append((test_num, in_file.name))
    
    # Add edge orphans in order
    for _, name in sorted(edge_orphans):
        orphaned_inputs.append(name)
    
    logger.info("Found %d orphaned example(s), %d orphaned numbered test(s), and %d orphaned edge test(s)", 
                len(orphaned_inputs) - len(numbered_orphans) - len(edge_orphans),
                len(numbered_orphans), len(edge_orphans))
    return orphaned_inputs

def run_tests(solution_code: str, test_cases: List[Dict[str, str]], time_limit: float = 5.0) -> Dict:
    """
    Run tests against the provided solution code efficiently, reads results and performance
    stats from the sandbox output, and returns a detailed report.
    """
    logger.info("Starting efficient test execution for %d test cases", len(test_cases))
    
    if not test_cases:
        return {"summary": {"status": "SUCCESS", "passed": 0, "failed": 0, "total": 0}, "results": []}
        
    
    
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        
        # 1. Prepare the directory for the test suite
        (work_dir / "solution.cpp").write_text(solution_code, encoding="utf-8")
        for test_case in test_cases:
            (work_dir / test_case["name"]).write_text(test_case["input"], encoding="utf-8")

        # 2. Run the entire suite in a single container
        try:
            # This call executes runner.sh, which now creates .out and .prof files
            run_test_suite(
                solution_path=str(work_dir / "solution.cpp"),
                test_cases_dir=work_dir,
                time_limit=time_limit
            )
        except Exception as e:
            logger.error("Test suite execution failed with an exception: %s", e)
            return {"summary": {"status": "ERROR", "message": "Docker execution failed"}, "details": str(e), "results": []}

        # 3. Check the results and parse performance stats from .out and .prof files
        detailed_results = []
        passed_count, failed_count = 0, 0
        
        for i, test_case in enumerate(test_cases, 1):
            out_file = work_dir / test_case["name"].replace(".in", ".out")
            prof_file = work_dir / test_case["name"].replace(".in", ".prof")
            
            # Default values
            time_sec, mem_kb, exit_code = 0.0, 0, 1 # Default to runtime error
            status = "RUNTIME_ERROR"

            # Parse performance file if it exists
            if prof_file.exists():
                try:
                    stats_line = prof_file.read_text()
                    time_sec = float(re.search(r"TIME:([\d.]+)", stats_line).group(1))
                    mem_kb = int(re.search(r"MEM:(\d+)", stats_line).group(1))
                    exit_code = int(re.search(r"STATUS:(\d+)", stats_line).group(1))
                except (AttributeError, ValueError):
                    logger.warning(f"Could not parse stats from {prof_file.name}")
            
            # Determine status based on the content of the output file
            if not out_file.exists():
                status = "RUNTIME_ERROR"
                failed_count += 1
            else:
                actual_output = out_file.read_text().strip()
                expected_output = test_case["output"].strip()

                if actual_output == "TIMEOUT":
                    status = "TIME_LIMIT_EXCEEDED"
                    failed_count += 1
                elif actual_output == "RUNTIME_ERROR":
                    status = "RUNTIME_ERROR"
                    failed_count += 1
                elif actual_output != expected_output:
                    status = "WRONG_ANSWER"
                    failed_count += 1
                else:
                    status = "PASSED"
                    passed_count += 1
            
            detailed_results.append({
                "test_name": test_case["name"],
                "status": status,
                "execution_time_ms": round(time_sec * 1000, 2),
                "memory_usage_kb": mem_kb
            })
    
    final_status = "SUCCESS" if failed_count == 0 else "FAILURE"
    summary = {"status": final_status, "passed": passed_count, "failed": failed_count, "total": len(test_cases)}
    logger.info("Test Summary: %d/%d tests passed", passed_count, len(test_cases))

    return {"summary": summary, "results": detailed_results}
