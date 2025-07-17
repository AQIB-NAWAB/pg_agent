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

def build_test_generator_graph(mode: str, refine: bool = False) -> StateGraph:
    """Builds the graph for generating test cases and validator.
    
    Args:
        mode: Either 'small', 'stress', or 'validator' to determine which generator to use
        refine: Whether to refine existing generator instead of creating new one
    """
    workflow = StateGraph(TestCaseGeneratorState)
    
    # Add nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("gen_small_tests", gen_small_tests_node)
    workflow.add_node("gen_stress_tests", gen_stress_tests_node)
    workflow.add_node("gen_validator", gen_validator_node)
    
    # Define flow based on mode
    workflow.set_entry_point("load_context")
    
    if mode == "small":
        workflow.add_edge("load_context", "gen_small_tests")
        workflow.add_edge("gen_small_tests", END)
    elif mode == "stress":
        workflow.add_edge("load_context", "gen_stress_tests")
        workflow.add_edge("gen_stress_tests", END)
    else:  # validator
        workflow.add_edge("load_context", "gen_validator")
        workflow.add_edge("gen_validator", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate test cases and validator for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Add generator type options
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--small", action="store_true", default=True,
                      help="Generate small test cases (default)")
    group.add_argument("--stress", action="store_true",
                      help="Generate stress test cases")
    group.add_argument("--validator", action="store_true",
                      help="Generate test case validator")
    
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

    # Determine mode
    mode = "validator" if args.validator else ("stress" if args.stress else "small")

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
        "mode": mode  # Add current mode to state
    }

    # Run the workflow
    graph = build_test_generator_graph(mode, args.refine is not None)
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        
        # Check if we have the required output based on mode
        output_path = None
        if mode == "small" and final_state.get("small_test_gen_path"):
            output_path = final_state["small_test_gen_path"]
            print(f"Small tests generator created successfully: {output_path}")
        elif mode == "stress" and final_state.get("stress_test_gen_path"):
            output_path = final_state["stress_test_gen_path"]
            print(f"Stress tests generator created successfully: {output_path}")
        elif mode == "validator" and final_state.get("validator_path"):
            output_path = final_state["validator_path"]
            print(f"Test case validator created successfully: {output_path}")
            
        if not output_path:
            print(f"Failed to generate {mode} script.")
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