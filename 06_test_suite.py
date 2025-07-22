#!/usr/bin/env python3
import os
import sys
import json
import argparse
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from pg_agent.nodes.test_suite_nodes import (
    TestSuiteState,
    load_scripts_node,
    validate_inputs_node,
    generate_outputs_node,
    finalize_node,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths

def build_test_suite_graph(mode: str = "outputs") -> StateGraph:
    """Builds the graph for test suite generation and validation workflow.
    
    Args:
        mode: The generation mode to use ("validator" or "outputs")
    """
    workflow = StateGraph(TestSuiteState)
    
    # Add nodes
    workflow.add_node("load_scripts", load_scripts_node)
    workflow.add_node("validate_inputs", validate_inputs_node)
    workflow.add_node("generate_outputs", generate_outputs_node)
    workflow.add_node("finalize", finalize_node)
    
    # Define flow based on mode
    workflow.set_entry_point("load_scripts")
    
    if mode == "validator":
        workflow.add_edge("load_scripts", "validate_inputs")
        workflow.add_edge("validate_inputs", "finalize")
    else:  # outputs mode
        workflow.add_edge("load_scripts", "generate_outputs")
        workflow.add_edge("generate_outputs", "finalize")
    
    workflow.add_edge("finalize", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""
    load_dotenv()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(
        description="Generate outputs and validate test cases for a programming problem"
    )
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Add time limit option for bruteforce solution
    parser.add_argument("--time-limit", type=float, default=2.0,
                       help="Time limit in seconds for solution execution (default: 2.0)")
    
    # Update mode choices
    parser.add_argument("--mode", type=str, default="outputs",
                       choices=["validator", "outputs"],
                       help="Operation mode: validator (validate test inputs) or outputs (generate outputs)")
    
    # Add solution selection flag
    parser.add_argument("--use-optimal", action="store_true",
                       help="Use optimal solution (standard.cpp) instead of bruteforce solution (solution_bf.cpp) for output generation")
    
    # Add logging control arguments
    parser.add_argument("--log-level", type=str, default="info",
                       choices=['debug', 'info', 'warning', 'error', 'critical'],
                       help="Set the logging level (default: info)")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress all output except errors (equivalent to --log-level error)")
    
    args = parser.parse_args()

    # Handle quiet mode and setup logging
    if args.quiet:
        log_level = logging.ERROR
    else:
        log_level = get_log_level(args.log_level)

    # Setup logging with the specified level
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    if not args.problem_dir:
        parser.error("No problem directory specified and could not read default from settings")

    # Get problem paths and validate required files exist
    paths = get_problem_paths(args.problem_dir)
    
    if not paths.problem_statement.exists():
        logger.error("Problem statement not found at %s", paths.problem_statement)
        sys.exit(1)

    # Check required files based on mode
    if args.mode == "validator":
        if not paths.root_validator.exists() and not paths.automation_validator.exists():
            logger.error("Validator not found at either:")
            logger.error("  - %s", paths.root_validator)
            logger.error("  - %s", paths.automation_validator)
            logger.error("Please run test generator workflow first or create validator manually.")
            sys.exit(1)
    else:  # outputs mode
        solution_path = paths.standard_solution if args.use_optimal else paths.bruteforce_solution
        if not solution_path.exists():
            logger.error("Solution not found at %s", solution_path)
            if args.use_optimal:
                logger.error("Please ensure standard.cpp exists or use --use-optimal flag.")
            else:
                logger.error("Please ensure solution_bf.cpp exists or run bruteforce generator first.")
            sys.exit(1)

    # Prepare initial state
    initial_state: TestSuiteState = {
        "problem_dir_path": str(paths.root),
        "bruteforce_time_limit": args.time_limit,
        "generation_mode": args.mode,
        "use_optimal": args.use_optimal,
        "solution_path": "",  # Will be loaded by load_scripts
        "validator_path": "",
        "run_dir_path": "",
        "valid_test_inputs": None,
        "invalid_tests": None
    }

    # Run the workflow
    graph = build_test_suite_graph(mode=args.mode)
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
            
    except Exception as e:
        logger.error("\nError occurred:")
        logger.error("="*60)
        logger.error(traceback.format_exc())
        logger.error("="*60)
        logger.error("Error message: %s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main() 