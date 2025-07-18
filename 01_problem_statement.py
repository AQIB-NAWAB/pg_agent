import os
import sys
import json
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.problem_setup_nodes import (
    setup_problem_directory,
    ProblemSetupState,
)
from pg_agent.nodes.problem_definition_nodes import (
    generate_problem_statement,
    refine_problem_statement,
    extract_examples,
    ProblemDefinitionState,
)
from pg_agent.utils.logging import setup_logging
from pg_agent.utils.structure import get_default_problem_dir
from pg_agent.nodes.topic_selector import select_random_topics

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
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Create a new programming problem non-interactively")
    parser.add_argument("output_dir", nargs="?", default=default_dir,
                       help=f"Path for the new problem directory (default: {default_dir})")
    
    # Create mutually exclusive group for the options, but make it optional
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("--topics", help="Create a problem from randomly selected topics or specified comma-separated list")
    mode_group.add_argument("--idea", help="Create a problem from an initial problem idea or concept")
    mode_group.add_argument("--refine", help="Refine an existing problem statement with feedback")
    
    # Add verbose flag
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging output")
    
    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    if not args.output_dir:
        parser.error("No output directory specified and could not read default from settings")

    # If no topics provided and not using idea or refine mode, select random topics
    if not any([args.topics, args.idea, args.refine]):
        topics_list = select_random_topics()
        args.topics = ", ".join(topics_list)
        print(f"No topics specified. Using randomly selected topics: '{args.topics}'")

    # Prepare initial state with all required fields from ProblemDefinitionState
    initial_state: ProblemDefinitionState = {
        "output_dir": os.path.abspath(args.output_dir),
        "topics": args.topics,
        "user_prompt": args.idea,
        "human_feedback": args.refine,
        "previous_problem": None,
        "problem_statement": "",
        "test_cases": [],
    }

    # Choose the appropriate graph based on whether we're refining
    graph = build_refine_graph() if args.refine else build_create_graph()
    
    try:
        final_state = graph.invoke(initial_state)
        print("\n--- Workflow Finished ---")
        print(f"Problem created successfully in: {final_state['output_dir']}")
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 