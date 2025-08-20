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
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env

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
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate simple test cases for an existing problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to the problem directory (default: {default_dir})")
    parser.add_argument("--model", type=str, choices=get_available_models("manual_tests"), default=default_model("manual_tests"),
                        help=f"Model to use (default: {default_model('manual_tests')})")
    # Add logging control arguments
    parser.add_argument("--log-level", type=str, default="info",
                        choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="Set the logging level (default: info)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress all output except errors (equivalent to --log-level error)")
    
    # Add parse flag
    parser.add_argument("--parse", action="store_true",
                        help="Parse tests from latest raw response instead of generating new ones")
    
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

    # Get problem paths and verify problem statement exists
    paths = get_problem_paths(args.problem_dir)
    if not args.parse and not paths.problem_statement.exists():
        logger.error("Problem statement not found at %s", paths.problem_statement)
        sys.exit(1)

    # Read the existing problem statement if not in parse-only mode
    problem_statement = ""
    if not args.parse:
        problem_statement = paths.problem_statement.read_text(encoding="utf-8")

    # Load model
    model_config = load_env(model=args.model)
    llm = get_llm(model_config)

    # Prepare initial state with only the required fields for test case generation
    initial_state: SimpleTestGenerationState = {
        "output_dir": str(paths.root),
        "problem_statement": problem_statement,
        "test_cases": [],
        "parse_only": args.parse,
        "llm": llm
    }

    # Run the workflow
    graph = build_test_cases_creator_graph()
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        if final_state.get("test_cases"):
            logger.info("Generated %d test cases successfully in: %s/test_cases/", 
                     len(final_state['test_cases']), paths.root)
        else:
            logger.error("Failed to generate test cases.")
            sys.exit(1)
    except Exception as e:
        logger.error("Error: %s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main() 