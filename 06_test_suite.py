#!/usr/bin/env python3
import os
import sys
import json
import argparse
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.test_suite_nodes import (
    TestSuiteState,
    load_scripts_node,
    run_generators_node,
    validate_inputs_node,
    run_bruteforce_on_small_tests_node,
    save_results_node,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir

def build_test_suite_graph() -> StateGraph:
    """Builds the graph for test suite generation and validation workflow."""
    workflow = StateGraph(TestSuiteState)
    
    # Add nodes
    workflow.add_node("load_scripts", load_scripts_node)
    workflow.add_node("run_generators", run_generators_node)
    workflow.add_node("validate_inputs", validate_inputs_node)
    workflow.add_node("run_bruteforce", run_bruteforce_on_small_tests_node)
    workflow.add_node("save_results", save_results_node)
    
    # Define sequential flow
    workflow.set_entry_point("load_scripts")
    workflow.add_edge("load_scripts", "run_generators")
    workflow.add_edge("run_generators", "validate_inputs")
    workflow.add_edge("validate_inputs", "run_bruteforce")
    workflow.add_edge("run_bruteforce", "save_results")
    workflow.add_edge("save_results", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(
        description="Generate, validate, and save a complete test suite for a programming problem"
    )
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Add time limit option for bruteforce solution
    parser.add_argument("--time-limit", type=float, default=2.0,
                       help="Time limit in seconds for bruteforce solution (default: 2.0)")
    
    # Add options to skip certain steps
    parser.add_argument("--skip-small", action="store_true",
                       help="Skip small test case generation")
    parser.add_argument("--skip-large", action="store_true",
                       help="Skip large/stress test case generation")
    
    # Add verbose flag
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging output")
    
    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    if not args.problem_dir:
        parser.error("No problem directory specified and could not read default from settings")

    problem_dir = Path(args.problem_dir)
    problem_statement_path = problem_dir / "problem_statement.md"
    
    if not problem_statement_path.exists():
        print(f"Error: Problem statement not found at {problem_statement_path}")
        sys.exit(1)

    # Check for required files
    automation_dir = problem_dir / "automation"
    settings_path = automation_dir / "automation_settings.json"
    if not settings_path.exists():
        print("Error: automation_settings.json not found. Please run previous workflows first.")
        sys.exit(1)

    # Prepare initial state
    initial_state: TestSuiteState = {
        "problem_dir_path": str(problem_dir),
        "bruteforce_time_limit": args.time_limit,
        "skip_small_tests": args.skip_small,
        "skip_large_tests": args.skip_large,
        "bruteforce_path": "",  # Will be loaded by load_scripts
        "small_test_gen_path": "",
        "stress_test_gen_path": "",
        "validator_path": "",
        "run_dir_path": "",
        "valid_small_tests": None,
        "valid_large_tests": None,
        "invalid_tests": None,
        "final_verdict": None
    }

    # Run the workflow
    graph = build_test_suite_graph()
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        
        # Print summary
        if final_state.get("final_verdict") == "SUCCESS":
            print("\nTest Suite Generation Summary:")
            if not args.skip_small:
                valid_small = len(final_state.get("valid_small_tests", []))
                print(f"- Small Tests: {valid_small} valid test cases")
            if not args.skip_large:
                valid_large = len(final_state.get("valid_large_tests", []))
                print(f"- Large Tests: {valid_large} valid test cases")
            
            invalid_count = len(final_state.get("invalid_tests", []))
            if invalid_count > 0:
                print(f"\nWarning: {invalid_count} invalid test cases were detected.")
                print("Check 'automation/testcases/invalid_testcases.json' for details.")
            
            print(f"\nTest suite saved to: {problem_dir}/automation/testcases/")
        else:
            print("Failed to generate complete test suite.")
            sys.exit(1)
            
    except Exception as e:
        print("\nError occurred:")
        print("="*60)
        traceback.print_exc()
        print("="*60)
        print(f"Error message: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 