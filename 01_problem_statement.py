import os
import sys
import argparse
import logging
from langgraph.graph import StateGraph, END

from pg_agent.nodes.problem_setup_nodes import (
    setup_problem_directory,
)
from pg_agent.nodes.problem_definition_nodes import (
    generate_problem_statement,
    refine_problem_statement,
    extract_examples,
    ProblemDefinitionState,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir
from pg_agent.nodes.topic_selector import select_random_topics
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env


def build_refine_graph() -> StateGraph:
    """Builds the graph for refining an existing problem."""
    workflow = StateGraph(ProblemDefinitionState)
    
    workflow.add_node("refine", refine_problem_statement)
    workflow.add_node("examples", extract_examples)
    
    workflow.set_entry_point("refine")
    workflow.add_edge("refine", "examples")
    workflow.add_edge("examples", END)
    
    return workflow.compile()

def build_create_graph() -> StateGraph:
    """Builds the graph for creating a new problem."""
    workflow = StateGraph(ProblemDefinitionState)
    
    workflow.add_node("setup", setup_problem_directory)
    workflow.add_node("generate", generate_problem_statement)
    workflow.add_node("examples", extract_examples)
    
    workflow.set_entry_point("setup")
    workflow.add_edge("setup", "generate")
    workflow.add_edge("generate", "examples")
    workflow.add_edge("examples", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Create a new programming problem non-interactively")
    parser.add_argument("output_dir", nargs="?", default=default_dir,
                        help=f"Path for the new problem directory (default: {default_dir})")
    
    # Create mutually exclusive group for the options, but make it optional
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("--topics", help="Create a problem from randomly selected topics or specified comma-separated list")
    mode_group.add_argument("--idea", help="Create a problem from an initial problem idea or concept")
    mode_group.add_argument("--refine", help="Refine an existing problem statement with feedback")
    parser.add_argument("--model", type=str, choices=get_available_models("problem_statement"), default=default_model("problem_statement"),
                        help=f"Model to use (default: {default_model('problem_statement')})") 
    # Add original problem argument
    parser.add_argument("--original", help="Path to an original problem to use as inspiration")
    
    # Add logging control arguments
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

    if not args.output_dir:
        parser.error("No output directory specified and could not read default from settings")

    # If no topics provided and not using idea or refine mode, select random topics
    if not any([args.topics, args.idea, args.refine]):
        topics_list = select_random_topics()
        args.topics = ", ".join(topics_list)
        logger.info("No topics specified. Using randomly selected topics: '%s'", args.topics)

    # Load original problem if specified
    previous_problem = None
    if args.original:
        try:
            with open(args.original, 'r', encoding='utf-8') as f:
                previous_problem = f.read()
        except Exception as e:
            parser.error(f"Failed to read original problem file: {str(e)}")

    # Load model
    model_config = load_env(model=args.model)
    llm = get_llm(model_config)

    # Prepare initial state with all required fields from ProblemDefinitionState
    initial_state: ProblemDefinitionState = {
        "output_dir": os.path.abspath(args.output_dir),
        "topics": args.topics,
        "user_prompt": args.idea,
        "human_feedback": args.refine,
        "previous_problem": previous_problem,
        "problem_statement": "",
        "test_cases": [],
        "llm": llm
    }

    # Choose the appropriate graph based on whether we're refining
    graph = build_refine_graph() if args.refine else build_create_graph()
    
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        logger.info("Problem created successfully in: %s", final_state['output_dir'])
    except Exception as e:
        logger.error("Error: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main() 