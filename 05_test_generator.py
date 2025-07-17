import os
import sys
import json
import argparse
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.test_generator_nodes import (
    TestCaseGeneratorState,
    load_context_node,
    gen_small_tests_node,
    gen_stress_tests_node,
    gen_validator_node,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir

def build_test_generator_graph(skip_small: bool = False, skip_stress: bool = False, skip_validator: bool = False) -> StateGraph:
    """Builds the graph for generating test cases and validator.
    
    Args:
        skip_small: Whether to skip small test generation
        skip_stress: Whether to skip stress test generation
        skip_validator: Whether to skip validator generation
    """
    workflow = StateGraph(TestCaseGeneratorState)
    
    # Add nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("gen_small_tests", gen_small_tests_node)
    workflow.add_node("gen_stress_tests", gen_stress_tests_node)
    workflow.add_node("gen_validator", gen_validator_node)
    
    # Define flow based on skip flags
    workflow.set_entry_point("load_context")
    
    # Track the last node to chain the flow
    last_node = "load_context"
    
    # Add each generator if not skipped
    if not skip_small:
        workflow.add_edge(last_node, "gen_small_tests")
        last_node = "gen_small_tests"
    
    if not skip_stress:
        workflow.add_edge(last_node, "gen_stress_tests")
        last_node = "gen_stress_tests"
    
    if not skip_validator:
        workflow.add_edge(last_node, "gen_validator")
        last_node = "gen_validator"
    
    # Connect last node to END
    workflow.add_edge(last_node, END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate test cases and validator for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Replace generator type options with skip flags
    parser.add_argument("--skip-small", action="store_true",
                      help="Skip generating small test cases")
    parser.add_argument("--skip-stress", action="store_true",
                      help="Skip generating stress test cases")
    parser.add_argument("--skip-validator", action="store_true",
                      help="Skip generating test case validator")
    
    # Add refine option with feedback
    parser.add_argument("--refine", metavar="FEEDBACK",
                       help="Refine existing generator/validator with the provided feedback")
    
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

    # Check for bruteforce solution
    automation_dir = problem_dir / "automation"
    settings_path = automation_dir / "automation_settings.json"
    if not settings_path.exists():
        print("Error: automation_settings.json not found. Please run bruteforce generator first.")
        sys.exit(1)

    # Prepare initial state
    initial_state: TestCaseGeneratorState = {
        "problem_dir_path": str(problem_dir),
        "problem_statement": "",  # Will be loaded by load_context
        "bruteforce_code": "",   # Will be loaded by load_context
        "small_test_gen_path": None,
        "stress_test_gen_path": None,
        "validator_path": None,
        "final_verdict": None,
        "refine_mode": args.refine is not None,  # True if --refine is provided
        "user_feedback": args.refine or "",  # Use feedback from --refine argument
        "skip_small": args.skip_small,
        "skip_stress": args.skip_stress,
        "skip_validator": args.skip_validator
    }

    # Run the workflow
    graph = build_test_generator_graph(
        skip_small=args.skip_small,
        skip_stress=args.skip_stress,
        skip_validator=args.skip_validator
    )
    
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        
        # Report status for each component
        if not args.skip_small:
            if final_state.get("small_test_gen_path"):
                print(f"✓ Small tests generator created: {final_state['small_test_gen_path']}")
            else:
                print("✗ Failed to generate small tests")
                
        if not args.skip_stress:
            if final_state.get("stress_test_gen_path"):
                print(f"✓ Stress tests generator created: {final_state['stress_test_gen_path']}")
            else:
                print("✗ Failed to generate stress tests")
                
        if not args.skip_validator:
            if final_state.get("validator_path"):
                print(f"✓ Test case validator created: {final_state['validator_path']}")
            else:
                print("✗ Failed to generate validator")
        
        # Check if any requested component failed
        if ((not args.skip_small and not final_state.get("small_test_gen_path")) or
            (not args.skip_stress and not final_state.get("stress_test_gen_path")) or
            (not args.skip_validator and not final_state.get("validator_path"))):
            print("\nSome components failed to generate.")
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