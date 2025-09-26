import sys
import argparse
import logging
import traceback
from pathlib import Path
from langgraph.graph import StateGraph, END

from pg_agent.nodes.bruteforce_nodes import (
    BruteForceState,
    load_problem_statement_node,
    generate_or_refine_bruteforce_node,
    test_bruteforce_node,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env, get_settings

def build_bruteforce_graph() -> StateGraph:
    """Builds the graph for generating and refining bruteforce solutions."""
    workflow = StateGraph(BruteForceState)
    
    # Single flow: load -> generate/refine -> test -> end
    workflow.add_node("load", load_problem_statement_node)
    workflow.add_node("generate_or_refine", generate_or_refine_bruteforce_node)
    workflow.add_node("test", test_bruteforce_node)
    
    workflow.set_entry_point("load")
    workflow.add_edge("load", "generate_or_refine")
    workflow.add_edge("generate_or_refine", "test")
    workflow.add_edge("test", END)
    
    return workflow.compile()

def get_next_version(problem_dir: Path) -> int:
    """Get the next version number for bruteforce solution."""
    paths = get_problem_paths(str(problem_dir))
    settings = paths.get_settings()  # This safely handles missing or invalid settings file
    return settings.get("bruteforceSolutionVersion", -1) + 1

def main():
    """Parse command line arguments and run the workflow."""
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate a bruteforce solution for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to the problem directory (default: {default_dir})")
    parser.add_argument("--refine", type=str, nargs='?', const='',
                        help="Refine previous solution. Optionally provide feedback for improvement.")
    parser.add_argument("--model", type=str, choices=get_available_models("bruteforce_sol"), default=default_model("bruteforce_sol"),
                        help=f"Model to use (default: {default_model('bruteforce_sol')})")
    parser.add_argument("-l", "--language", type=str, choices=["C++", "Python", "default"], default="default",
                        help="Programming language to use: C++, Python, or default (from settings) (default: default)")
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

    # Load model
    model_config = load_env(model=args.model)
    llm = get_llm(model_config)

    # Determine language to use
    if args.language == "default":
        settings = get_settings()
        language = settings.get("language", "C++")
        logger.info(f"Using language from settings: {language}")
    else:
        language = args.language
        logger.info(f"Using language from command line: {language}")

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
        "final_bruteforce_path": None,
        "llm": llm,
        "language": language
    }

    # Run the workflow
    graph = build_bruteforce_graph()
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")

        # Check if we have a successful solution
        if final_state.get("final_verdict") == "SUCCESS":
            logger.info("Bruteforce solution generated successfully in: %s",
                        final_state.get('final_bruteforce_path'))
        elif final_state.get("test_failures"):
            logger.warning("Solution failed some tests. Use --refine to improve it or change the model by using --model.")
            if not args.refine:
                logger.info("Example: %s --refine or --model \"Fix the edge case with negative numbers\"", sys.argv[0])
            sys.exit(1)
        else:
            logger.error("Failed to generate a working bruteforce solution - unknown error.")
            sys.exit(1)

    except Exception as e:
        logger.error("Error occurred:")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        logger.error("Error message: %s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
