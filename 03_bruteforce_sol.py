import os
import sys
import json
import argparse
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.bruteforce_nodes import (
    BruteForceState,
    load_problem_statement,
    generate_bruteforce,
    test_bruteforce,
    refine_bruteforce,
    save_solution,
    should_refine,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir

def build_bruteforce_graph() -> StateGraph:
    """Builds the graph for generating and refining bruteforce solutions."""
    workflow = StateGraph(BruteForceState)
    
    workflow.add_node("load", load_problem_statement)
    workflow.add_node("generate", generate_bruteforce)
    workflow.add_node("test", test_bruteforce)
    workflow.add_node("refine", refine_bruteforce)
    workflow.add_node("save", save_solution)
    
    workflow.set_entry_point("load")
    workflow.add_edge("load", "generate")
    workflow.add_edge("generate", "test")
    
    workflow.add_conditional_edges(
        "test",
        should_refine,
        {
            "refine": "refine",
            "save": "save",
            "end_failure": END,
        }
    )
    
    workflow.add_edge("refine", "test")
    workflow.add_edge("save", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate a bruteforce solution for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    parser.add_argument("--max-iterations", type=int, default=2,
                       help="Maximum number of refinement iterations (default: 2)")
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

    # Prepare initial state
    initial_state: BruteForceState = {
        "problem_dir_path": str(problem_dir),
        "problem_statement": "",
        "example_test_cases": [],
        "bruteforce_code": None,
        "test_failures": [],
        "iteration_count": 0,
        "max_iterations": args.max_iterations,
        "human_feedback": None,
        "final_verdict": None,
        "final_bruteforce_path": None
    }

    # Run the workflow
    graph = build_bruteforce_graph()
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        
        # Check if we have a successful solution
        if final_state.get("final_verdict") == "SUCCESS":
            print(f"Bruteforce solution generated successfully in: {final_state.get('final_bruteforce_path')}")
        elif final_state.get("test_failures"):
            print("Failed to generate a working bruteforce solution - some test cases failed.")
            sys.exit(1)
        else:
            print("Failed to generate a working bruteforce solution - unknown error.")
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