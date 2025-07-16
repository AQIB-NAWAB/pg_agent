import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import TypedDict, List, Tuple
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.test_generation_nodes import (
    generate_test_cases,
    TestGenerationState,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir

def build_test_cases_creator_graph() -> StateGraph:
    """Builds a minimal graph that only generates example test cases."""
    # Initialize with our simplified state type
    workflow = StateGraph(TestGenerationState)

    # Add just the test cases generation node
    workflow.add_node("generate_tests", generate_test_cases)

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
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging output")
    
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

    # Read the existing problem statement
    problem_statement = problem_statement_path.read_text(encoding="utf-8")

    # Prepare initial state with only the required fields for test case generation
    initial_state: TestGenerationState = {
        "output_dir": str(problem_dir),
        "problem_statement": problem_statement,
        "test_cases": [],
    }

    # Run the workflow
    graph = build_test_cases_creator_graph()
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        print(f"Simple test cases generated successfully in: {final_state['output_dir']}/test_cases/")
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 