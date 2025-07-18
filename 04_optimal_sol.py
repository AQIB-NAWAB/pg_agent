import os
import sys
import json
import argparse
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.optimal_nodes import (
    OptimalSolutionState,
    load_context,
    generate_optimal,
    test_optimal,
    fix_optimal,
    save_solution,
    should_fix,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir

def build_optimal_graph() -> StateGraph:
    """Builds the graph for generating and refining optimal solutions."""
    workflow = StateGraph(OptimalSolutionState)
    
    workflow.add_node("load", load_context)
    workflow.add_node("generate", generate_optimal)
    workflow.add_node("test", test_optimal)
    workflow.add_node("fix", fix_optimal)
    workflow.add_node("save", save_solution)
    
    workflow.set_entry_point("load")
    workflow.add_edge("load", "generate")
    workflow.add_edge("generate", "test")
    
    workflow.add_conditional_edges(
        "test",
        should_fix,
        {
            "fix": "fix",
            "save": "save",
            "end_failure": END,
        }
    )
    
    workflow.add_edge("fix", "test")
    workflow.add_edge("save", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate an optimal solution for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    parser.add_argument("--max-iterations", type=int, default=2,
                       help="Maximum number of refinement iterations (default: 2)")
    parser.add_argument("--time-limit", type=float, default=5,
                       help="Time limit for solution execution in seconds (default: 5)")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging output")
    parser.add_argument("--refine", metavar="FEEDBACK",
                       help="Provide feedback to refine the existing optimal solution")
    
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

    # If refining, check that optimal solution exists
    if args.refine:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        optimal_version = settings.get("optimalSolutionVersion", -1)
        if optimal_version == -1:
            print("Error: No optimal solution found to refine. Please run without --refine first.")
            sys.exit(1)

    # Prepare initial state
    initial_state: OptimalSolutionState = {
        "problem_dir_path": str(problem_dir),
        "problem_statement": "",  # Will be loaded by load_context
        "bruteforce_code": "",   # Will be loaded by load_context
        "example_test_cases": [],  # Will be loaded by load_context
        "optimal_code": None,
        "test_failures": [],
        "iteration_count": 0,
        "max_iterations": args.max_iterations,
        "time_limit": args.time_limit,
        "human_feedback": args.refine,  # Use feedback from --refine argument
        "final_verdict": None,
        "final_optimal_path": None
    }

    # Run the workflow
    graph = build_optimal_graph()
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        
        # Check if we have a successful solution
        if final_state.get("final_verdict") == "SUCCESS":
            print(f"Optimal solution generated successfully in: {final_state.get('final_optimal_path')}")
        elif final_state.get("test_failures"):
            print("\nFailed to generate a working optimal solution:")
            for failure in final_state["test_failures"]:
                print(f"- Test {failure['test_name']}: {failure['reason']}")
                if failure['reason'] == "Wrong Answer":
                    print(f"  Input: {failure['input']}")
                    print(f"  Expected: {failure['expected']}")
                    print(f"  Got: {failure['actual']}")
            sys.exit(1)
        else:
            print("Failed to generate a working optimal solution - unknown error.")
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
