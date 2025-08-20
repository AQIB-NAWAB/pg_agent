import sys
import argparse
import logging
import traceback
from langgraph.graph import StateGraph, END
from pg_agent.nodes.test_generator_nodes import (
    TestCaseGeneratorState,
    load_context_node,
    gen_basic_tests_node,
    gen_edge_tests_node,
    gen_validator_node,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env

def build_test_generator_graph(mode: str = "basic") -> StateGraph:
    """Builds the graph for generating test cases and validator.
    
    Args:
        mode: The generation mode to use ("basic", "edge", "validator", or "all")
    """
    workflow = StateGraph(TestCaseGeneratorState)
    
    # Add nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("gen_basic_tests", gen_basic_tests_node)
    workflow.add_node("gen_edge_tests", gen_edge_tests_node)
    workflow.add_node("gen_validator", gen_validator_node)
    
    # Define flow based on mode
    workflow.set_entry_point("load_context")
    
    if mode == "basic" or mode == "all":
        workflow.add_edge("load_context", "gen_basic_tests")
        if mode == "basic":
            workflow.add_edge("gen_basic_tests", END)
    
    if mode == "edge" or mode == "all":
        prev_node = "gen_basic_tests" if mode == "all" else "load_context"
        workflow.add_edge(prev_node, "gen_edge_tests")
        if mode == "edge":
            workflow.add_edge("gen_edge_tests", END)
    
    if mode == "validator" or mode == "all":
        prev_node = "gen_edge_tests" if mode == "all" else "load_context"
        workflow.add_edge(prev_node, "gen_validator")
        workflow.add_edge("gen_validator", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate test cases and validator for a programming problem")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to the problem directory (default: {default_dir})")
    
    # Replace skip flags with mode selection
    parser.add_argument("--mode", type=str, default="basic",
                        choices=["basic", "edge", "validator", "all"],
                        help="Generation mode: basic (50 tests), edge (5-10 edge cases), "
                             "validator (test case validator), or all (run all modes)")

    parser.add_argument("--model", type=str, choices=get_available_models("test_generator"), default=default_model("test_generator"),
                        help=f"Model to use (default: {default_model('test_generator')})")
    
    # Add refine option with feedback
    parser.add_argument("--refine", metavar="FEEDBACK",
                        help="Refine existing generator/validator with the provided feedback")
    
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

    # Get problem paths using utility function
    problem_paths = get_problem_paths(args.problem_dir)
    
    if not problem_paths.problem_statement.exists():
        logger.error("Problem statement not found at %s", problem_paths.problem_statement)
        sys.exit(1)

    # Check for automation settings
    if not problem_paths.automation_settings.exists():
        logger.error("Error: automation_settings.json not found. Please run bruteforce generator first.")
        sys.exit(1)

    # Load model
    model_config = load_env(model=args.model)
    llm = get_llm(model_config)

    # Prepare initial state
    initial_state: TestCaseGeneratorState = {
        "problem_dir_path": str(problem_paths.root),
        "problem_statement": "",  # Will be loaded by load_context
        "bruteforce_code": "",   # Will be loaded by load_context
        "basic_test_gen_path": None,
        "edge_test_gen_path": None,
        "validator_path": None,
        "final_verdict": None,
        "refine_mode": args.refine is not None,  # True if --refine is provided
        "user_feedback": args.refine or "",  # Use feedback from --refine argument
        "generation_mode": args.mode,
        "llm": llm
    }

    # Run the workflow
    graph = build_test_generator_graph(mode=args.mode)
    
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        
        # Report status based on mode
        if args.mode in ["basic", "all"]:
            if final_state.get("basic_test_gen_path"):
                logger.info("✓ Basic test generator created: %s", final_state['basic_test_gen_path'])
            else:
                logger.error("✗ Failed to generate basic tests")
                
        if args.mode in ["edge", "all"]:
            if final_state.get("edge_test_gen_path"):
                logger.info("✓ Edge case generator created: %s", final_state['edge_test_gen_path'])
            else:
                logger.error("✗ Failed to generate edge cases")
                
        if args.mode in ["validator", "all"]:
            if final_state.get("validator_path"):
                logger.info("✓ Test case validator created: %s", final_state['validator_path'])
            else:
                logger.error("✗ Failed to generate validator")
        
        # Check if any requested component failed
        if ((args.mode in ["basic", "all"] and not final_state.get("basic_test_gen_path")) or
            (args.mode in ["edge", "all"] and not final_state.get("edge_test_gen_path")) or
            (args.mode in ["validator", "all"] and not final_state.get("validator_path"))):
            logger.error("Some components failed to generate.")
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