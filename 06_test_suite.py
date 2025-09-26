#!/usr/bin/env python3
import os
import sys
import json
import argparse
import logging
import traceback
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
from pg_agent.utils.env import get_settings

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

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(
        description="Generate outputs and validate test cases for a programming problem"
    )
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                       help=f"Path to the problem directory (default: {default_dir})")
    
    # Add time limit option for bruteforce solution
    parser.add_argument("--time-limit", type=float, default=5.0,
                       help="Time limit in seconds for bruteforce solution execution (default: 5.0)")

    # Update mode choices
    parser.add_argument("--mode", type=str, default="outputs",
                       choices=["validator", "outputs"],
                       help="Operation mode: validator (validate test inputs) or outputs (generate outputs)")
    
    # Replace --use-optimal with new flags
    parser.add_argument("--use-bf-only", action="store_true",
                       help="Use only bruteforce solution (solution_bf.cpp) for output generation")
    parser.add_argument("--use-opt-only", action="store_true",
                       help="Use only optimal solution (standard.cpp) for output generation")
    
    parser.add_argument("-l", "--language", type=str, choices=["C++", "Python", "default"], default="default",
                       help="Programming language to use: C++, Python, or default (from settings) (default: default)")
    
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

    # Determine language to use
    if args.language == "default":
        settings = get_settings()
        language = settings.get("language", "C++")
        logger.info(f"Using language from settings: {language}")
    else:
        language = args.language
        logger.info(f"Using language from command line: {language}")
    
    # Get problem paths and validate required files exist
    paths = get_problem_paths(args.problem_dir)
    
    if not paths.problem_statement.exists():
        logger.error("Problem statement not found at %s", paths.problem_statement)
        sys.exit(1)

    # Determine which solutions to run
    run_bruteforce = not args.use_opt_only  # Run bruteforce unless only optimal is requested
    run_optimal = not args.use_bf_only      # Run optimal unless only bruteforce is requested
    
    # Validate that at least one solution type is selected
    if not run_bruteforce and not run_optimal:
        logger.error("At least one solution type must be selected")
        sys.exit(1)

    # Check required files based on mode
    if args.mode == "validator":
        validator_path = paths.get_validator_path(language)
        if not validator_path.exists() and not paths.automation_validator.exists():
            logger.error("Validator not found at either:")
            logger.error("  - %s", validator_path)
            logger.error("  - %s", paths.automation_validator)
            logger.error("Please run test generator workflow first or create validator manually.")
            sys.exit(1)
    else:  # outputs mode
        # Check that at least one solution exists
        solutions_exist = False
        bruteforce_path = paths.get_bruteforce_solution_path(language)
        standard_path = paths.get_standard_solution_path(language)
        
        if run_bruteforce and bruteforce_path.exists():
            solutions_exist = True
        if run_optimal and standard_path.exists():
            solutions_exist = True
        
        if not solutions_exist:
            logger.error("No valid solutions found:")
            if run_bruteforce:
                logger.error("  - Bruteforce solution not found at %s", bruteforce_path)
            if run_optimal:
                logger.error("  - Optimal solution not found at %s", standard_path)
            logger.error("Please ensure required solution files exist or adjust the --use-bf-only/--use-opt-only flags.")
            sys.exit(1)

    # Prepare initial state - the generate_outputs_node will handle both solutions
    initial_state: TestSuiteState = {
        "problem_dir_path": str(paths.root),
        "bruteforce_time_limit": args.time_limit,
        "generation_mode": args.mode,
        "use_bruteforce": run_bruteforce,  # Whether to use bruteforce solution
        "use_optimal": run_optimal,        # Whether to use optimal solution
        "solutions_to_process": [],        # Will be populated by load_scripts_node
        "solution_path": "",               # Will be loaded by load_scripts
        "validator_path": "",
        "run_dir_path": "",
        "valid_test_inputs": None,
        "invalid_tests": None,
        "current_solution_index": 0,
        "language": language
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
