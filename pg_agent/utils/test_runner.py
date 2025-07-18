from pathlib import Path
from typing import Dict, List, Tuple
import re
import logging

from ..pipeline.sandbox.sandbox_utils import run_single_test

logger = logging.getLogger(__name__)

def find_test_cases(test_cases_dir: Path) -> List[Dict[str, str]]:
    """Find all test cases in the given directory.
    
    Looks for both example_*.in and test_*.in files and their corresponding .out files.
    Test cases are returned in order (examples first, then numbered tests).
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
            
    # Then collect numbered test cases
    logger.info("Looking for numbered test cases...")
    numbered_pairs = []
    for in_file in test_cases_dir.glob("test_*.in"):
        out_file = in_file.with_suffix(".out")
        if out_file.exists():
            # Extract test number for sorting
            match = re.search(r'test_(\d+)\.in', in_file.name)
            if match:
                test_num = int(match.group(1))
                logger.debug("Found test pair #%d: %s -> %s", test_num, in_file.name, out_file.name)
                numbered_pairs.append((test_num, in_file, out_file))
        else:
            logger.warning("Missing output file for %s", in_file.name)
    
    # Add numbered tests in order
    for _, in_file, out_file in sorted(numbered_pairs):
        test_cases.append({
            "input": in_file.read_text(encoding="utf-8"),
            "output": out_file.read_text(encoding="utf-8").strip(),
            "name": in_file.name
        })
    
    logger.info("Found %d example(s) and %d numbered test(s)", 
                len(example_pairs), len(numbered_pairs))
    return test_cases

def run_tests(solution_code: str, test_cases: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Run tests against the provided solution code.
    
    Args:
        solution_code: The code to test
        test_cases: List of test cases to run against
        
    Returns:
        List of test failures. Empty list means all tests passed.
        Failures can include compilation errors or runtime test failures.
    """
    logger.info("Starting test execution")
    failures = []
    
    if not test_cases:
        logger.warning("No test cases provided")
        return failures
    
    # Try first test case to check for compilation errors
    logger.info("Checking compilation...")
    passed, output, error = run_single_test(
        solution_code=solution_code,
        input_data=test_cases[0]["input"]
    )
    
    # If compilation failed, return it as a special failure
    if not passed and "error:" in error:
        logger.error("Compilation failed")
        return [{
            "test_number": 0,
            "test_name": "compilation",
            "input": "",
            "expected_output": "Successful compilation",
            "actual_output": output,
            "error": error,
            "is_compilation_error": True
        }]
    
    logger.info("Executing %d test cases...", len(test_cases))
    for i, test_case in enumerate(test_cases, 1):
        logger.info("Test #%d: %s", i, test_case['name'])
        logger.debug("Input: %s", test_case['input'].strip())
        logger.debug("Expected: %s", test_case['output'])
        
        passed, actual_output, error = run_single_test(
            solution_code=solution_code,
            input_data=test_case["input"]
        )
        
        actual_output_stripped = actual_output.strip()
        logger.debug("Actual: %s", actual_output_stripped)
        
        if not passed or actual_output_stripped != test_case["output"]:
            logger.error("Test #%d FAILED", i)
            failures.append({
                "test_number": i,
                "test_name": test_case["name"],
                "input": test_case["input"],
                "expected_output": test_case["output"],
                "actual_output": actual_output_stripped,
                "error": error if error else None,
                "is_compilation_error": False
            })
        else:
            logger.info("Test #%d PASSED", i)
            
    # Log summary
    total = len(test_cases)
    passed = total - len(failures)
    logger.info("Test Summary: %d/%d tests passed", passed, total)
    if failures:
        if any(f.get("is_compilation_error", False) for f in failures):
            logger.error("Compilation failed")
        else:
            logger.error("Failed tests: %s", 
                        ', '.join(f['test_name'] for f in failures))
            
    return failures 