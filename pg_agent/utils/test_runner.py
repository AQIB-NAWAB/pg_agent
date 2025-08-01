from pathlib import Path
from typing import Dict, List, Tuple
import re
import logging
import tempfile

from ..pipeline.sandbox.sandbox_utils import run_test_suite, run_single_test

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

def run_tests(solution_code: str, test_cases: List[Dict[str, str]], time_limit: float = 5.0) -> List[Dict[str, str]]:
    """Run tests against the provided solution code efficiently."""
    logger.info("Starting efficient test execution for %d test cases", len(test_cases))
    failures = []
    
    if not test_cases:
        logger.warning("No test cases provided")
        return failures
        
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        
        # 1. Prepare the directory for the test suite
        solution_path = work_dir / "solution.cpp"
        solution_path.write_text(solution_code, encoding="utf-8")
        
        for test_case in test_cases:
            (work_dir / test_case["name"]).write_text(test_case["input"], encoding="utf-8")

        # 2. Run the entire suite in a single container
        try:
            run_test_suite(
                solution_path=str(solution_path),
                test_cases_dir=work_dir,
                time_limit=time_limit
            )
        except Exception as e:
            logger.error("Test suite execution failed with an exception: %s", e)
            return [{"test_name": "suite_execution", "reason": str(e)}]

        # 3. Check the results
        for i, test_case in enumerate(test_cases, 1):
            out_file = work_dir / test_case["name"].replace(".in", ".out")
            
            if not out_file.exists():
                failures.append({
                    "test_number": i, "test_name": test_case["name"],
                    "reason": "Output file not created (likely runtime error)"
                })
                continue

            actual_output = out_file.read_text(encoding="utf-8").strip()
            expected_output = test_case["output"].strip()

            if actual_output == "TIMEOUT":
                logger.error("Test #%d FAILED (TIMEOUT)", i)
                failures.append({
                    "test_number": i, "test_name": test_case["name"],
                    "reason": "Time Limit Exceeded"
                })
            elif actual_output != expected_output:
                logger.error("Test #%d FAILED (Wrong Answer)", i)
                failures.append({
                    "test_number": i, "test_name": test_case["name"],
                    "input": test_case["input"],
                    "expected_output": expected_output,
                    "actual_output": actual_output,
                })
            else:
                logger.info("Test #%d PASSED", i)

    total = len(test_cases)
    passed_count = total - len(failures)
    logger.info("Test Summary: %d/%d tests passed", passed_count, total)
    if failures:
        logger.error("Failed tests: %s", ', '.join(f['test_name'] for f in failures))
            
    return failures