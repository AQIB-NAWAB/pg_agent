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
    load_problem_statement_node,
    generate_bruteforce_node,
    test_bruteforce_node,
    refine_bruteforce_node,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths

def get_log_level(level_name: str) -> int:
    """Convert log level name to logging constant."""
    return {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }.get(level_name.lower(), logging.INFO)

def build_bruteforce_graph(is_refinement: bool = False) -> StateGraph:
    """Builds the graph for generating and refining bruteforce solutions.
    
    Args:
        is_refinement: If True, runs refinement flow instead of generation
    """
    workflow = StateGraph(BruteForceState)
    
    if is_refinement:
        # Refinement flow: load -> refine -> test -> end
        workflow.add_node("load", load_problem_statement_node)
        workflow.add_node("refine", refine_bruteforce_node)
        workflow.add_node("test", test_bruteforce_node)
        
        workflow.set_entry_point("load")
        workflow.add_edge("load", "refine")
        workflow.add_edge("refine", "test")
        workflow.add_edge("test", END)
    else:
        # Generation flow: load -> generate -> test -> end
        workflow.add_node("load", load_problem_statement_node)
        workflow.add_node("generate", generate_bruteforce_node)
        workflow.add_node("test", test_bruteforce_node)
        
        workflow.set_entry_point("load")
        workflow.add_edge("load", "generate")
        workflow.add_edge("generate", "test")
        workflow.add_edge("test", END)
    
    return workflow.compile()

def get_next_version(problem_dir: Path) -> int:
    """Get the next version number for bruteforce solution."""
    paths = get_problem_paths(str(problem_dir))
    settings = paths.get_settings()  # This safely handles missing or invalid settings file
    return settings.get("bruteforceSolutionVersion", -1) + 1

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate a bruteforce solution for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    parser.add_argument("--refine", type=str, nargs='?', const='',
                       help="Refine previous solution. Optionally provide feedback for improvement.")
    parser.add_argument("--log-level", type=str, default="info",
                       choices=['debug', 'info', 'warning', 'error', 'critical'],
                       help="Set the logging level (default: info)")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress all output except errors (equivalent to --log-level error)")
    
    args = parser.parse_args()

    # Handle quiet mode
    if args.quiet:
        log_level = logging.ERROR
    else:
        log_level = get_log_level(args.log_level)

    # Setup logging with the specified level
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    if not args.problem_dir:
        parser.error("No problem directory specified and could not read default from settings")

    problem_dir = Path(args.problem_dir)
    problem_statement_path = problem_dir / "problem_statement.md"
    
    if not problem_statement_path.exists():
        logger.error("Problem statement not found at %s", problem_statement_path)
        sys.exit(1)

    # Get the next version number
    next_version = get_next_version(problem_dir)

    # Prepare initial state
    initial_state: BruteForceState = {
        "problem_dir_path": str(problem_dir),
        "problem_statement": "",
        "example_test_cases": [],
        "bruteforce_code": None,
        "test_failures": [],
        "iteration_count": next_version,
        "human_feedback": args.refine if args.refine is not None else None,
        "final_verdict": None,
        "final_bruteforce_path": None
    }

    # Run the workflow
    graph = build_bruteforce_graph(is_refinement=args.refine is not None)
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        
        # Check if we have a successful solution
        if final_state.get("final_verdict") == "SUCCESS":
            logger.info("Bruteforce solution generated successfully in: %s", 
                       final_state.get('final_bruteforce_path'))
        elif final_state.get("test_failures"):
            logger.warning("Solution failed some tests. Use --refine to improve it.")
            if not args.refine:
                logger.info("Example: %s --refine \"Fix the edge case with negative numbers\"", sys.argv[0])
            sys.exit(1)
        else:
            logger.error("Failed to generate a working bruteforce solution - unknown error.")
            sys.exit(1)
            
    except Exception as e:
        logger.error("Error occurred:")
        logger.error("="*60)
        logger.error(traceback.format_exc())
        logger.error("="*60)
        logger.error("Error message: %s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main() 