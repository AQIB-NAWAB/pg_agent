import os
import sys
import json
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.manual_tests_nodes import (
    SimpleTestGenerationState,
    generate_simple_test_cases,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths

def build_test_cases_creator_graph() -> StateGraph:
    """Builds a minimal graph that only generates example test cases."""
    # Initialize with our simplified state type
    workflow = StateGraph(SimpleTestGenerationState)

    # Add just the test cases generation node
    workflow.add_node("generate_tests", generate_simple_test_cases)

    # Set up the simple flow
    workflow.set_entry_point("generate_tests")
    workflow.add_edge("generate_tests", END)

    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate simple test cases for an existing problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Add verbose flag
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging output")
    
    # Add parse flag
    parser.add_argument("--parse", action="store_true",
                       help="Parse tests from latest raw response instead of generating new ones")
    
    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    if not args.problem_dir:
        parser.error("No problem directory specified and could not read default from settings")

    # Get problem paths and verify problem statement exists
    paths = get_problem_paths(args.problem_dir)
    if not args.parse and not paths.problem_statement.exists():
        print(f"Error: Problem statement not found at {paths.problem_statement}")
        sys.exit(1)

    # Read the existing problem statement if not in parse-only mode
    problem_statement = ""
    if not args.parse:
        problem_statement = paths.problem_statement.read_text(encoding="utf-8")

    # Prepare initial state with only the required fields for test case generation
    initial_state: SimpleTestGenerationState = {
        "output_dir": str(paths.root),
        "problem_statement": problem_statement,
        "test_cases": [],
        "parse_only": args.parse
    }

    # Run the workflow
    graph = build_test_cases_creator_graph()
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        if final_state.get("test_cases"):
            print(f"Generated {len(final_state['test_cases'])} test cases successfully in: {paths.root}/test_cases/")
        else:
            print("Failed to generate test cases.")
            sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 