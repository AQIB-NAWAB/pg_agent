import sys
import argparse
import logging
import traceback
from pathlib import Path
from langgraph.graph import StateGraph, END

from pg_agent.nodes.optimal_nodes import (
    OptimalSolutionState,
    load_context_node,
    generate_optimal_node,
    test_optimal_node,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env, get_settings

def get_next_version(problem_dir: Path) -> int:
    """Get the next version number for optimal solution."""
    paths = get_problem_paths(str(problem_dir))
    settings = paths.get_settings()
    return settings.get("optimalSolutionVersion", -1) + 1

def build_optimal_graph() -> StateGraph:
    """Builds the graph for generating and refining optimal solutions."""
    workflow = StateGraph(OptimalSolutionState)
    
    # Simple linear flow: load -> generate -> test -> end
    workflow.add_node("load", load_context_node)
    workflow.add_node("generate", generate_optimal_node)
    workflow.add_node("test", test_optimal_node)
    
    workflow.set_entry_point("load")
    workflow.add_edge("load", "generate")
    workflow.add_edge("generate", "test")
    workflow.add_edge("test", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate an optimal solution for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to the problem directory (default: {default_dir})")
    parser.add_argument("--model", type=str, choices=get_available_models("optimal_sol"), default=default_model("optimal_sol"),
                        help=f"Model to use (default: {default_model('optimal_sol')})")
    parser.add_argument("--refine", type=str, nargs='?', const='',
                        help="Refine previous solution. Optionally provide feedback for improvement.")
    parser.add_argument("--time-limit", type=float, default=5,
                        help="Time limit for solution execution in seconds (default: 5)")
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

    # If refining, check that optimal solution exists
    paths = get_problem_paths(str(problem_dir))
    if args.refine:
        settings = paths.get_settings()
        if settings.get("optimalSolutionVersion", -1) == -1:
            logger.error("No optimal solution found to refine. Please run without --refine first.")
            sys.exit(1)

    # Get the next version number
    next_version = get_next_version(problem_dir)

    # Load model
    model_config = load_env(model=args.model)
    llm = get_llm(model_config)

    # Load language setting from global settings
    settings = get_settings()
    language = settings.get("language", "C++")
    logger.info(f"Using language: {language}")

    # Prepare initial state
    initial_state: OptimalSolutionState = {
        "problem_dir_path": str(problem_dir),
        "problem_statement": "",  # Will be loaded by load_context
        "bruteforce_code": "",   # Will be loaded by load_context
        "example_test_cases": [],  # Will be loaded by load_context
        "optimal_code": None,
        "test_failures": [],
        "iteration_count": next_version,
        "time_limit": args.time_limit,
        "human_feedback": args.refine if args.refine is not None else None,
        "is_refinement": args.refine is not None,  # True if --refine was used
        "final_verdict": None,
        "final_optimal_path": None,
        "llm": llm,
        "language": language
    }

    # Run the workflow
    graph = build_optimal_graph()
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        
        # Check if we have a successful solution
        if final_state.get("final_verdict") == "SUCCESS":
            logger.info("Optimal solution generated successfully in: %s", 
                       final_state.get('final_optimal_path'))
        elif final_state.get("test_failures"):
            if any(f.get("is_compilation_error", False) for f in final_state["test_failures"]):
                logger.error("Compilation failed:")
                for failure in final_state["test_failures"]:
                    logger.error(failure["error"])
            else:
                logger.warning("Solution failed some tests. Use --refine to improve it.")
                if not args.refine:
                    logger.info("Example: %s --refine \"Fix the edge case with negative numbers\"", sys.argv[0])
            sys.exit(1)
        else:
            logger.error("Failed to generate a working optimal solution - unknown error.")
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
