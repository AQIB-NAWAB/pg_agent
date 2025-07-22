from pathlib import Path
from typing import Dict, List, Tuple
import re
import logging

from ..pipeline.sandbox.sandbox_utils import run_single_test

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