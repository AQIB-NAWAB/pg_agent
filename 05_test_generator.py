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
    run_basic_test_generator_node,
    run_edge_test_generator_node,
)
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.models import get_llm
from pg_agent.utils.env import get_available_models, default_model, load_env, get_settings

def build_test_generator_graph(mode: str = "basic", exec_only: bool = False) -> StateGraph:
    """Builds the graph for generating test cases and validator.
    
    Args:
        mode: The generation mode to use ("basic", "edge", "validator", or "all")
        exec_only: If True, skip generation and only execute existing generators
    """
    workflow = StateGraph(TestCaseGeneratorState)
    
    # Add nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("gen_basic_tests", gen_basic_tests_node)
    workflow.add_node("gen_edge_tests", gen_edge_tests_node)
    workflow.add_node("gen_validator", gen_validator_node)
    workflow.add_node("run_basic_generator", run_basic_test_generator_node)
    workflow.add_node("run_edge_generator", run_edge_test_generator_node)
    
    # Define flow based on mode and exec_only flag
    workflow.set_entry_point("load_context")
    
    if exec_only:
        # In exec-only mode, skip generation and go directly to execution
        if mode == "basic":
            workflow.add_edge("load_context", "run_basic_generator")
            workflow.add_edge("run_basic_generator", END)
        elif mode == "edge":
            workflow.add_edge("load_context", "run_edge_generator")
            workflow.add_edge("run_edge_generator", END)
        elif mode == "all":
            workflow.add_edge("load_context", "run_basic_generator")
            workflow.add_edge("run_basic_generator", "run_edge_generator")
            workflow.add_edge("run_edge_generator", END)
        else:  # validator mode
            # For validator mode in exec-only, we still need to generate it
            workflow.add_edge("load_context", "gen_validator")
            workflow.add_edge("gen_validator", END)
    else:
        # Normal generation mode
        if mode == "basic" or mode == "all":
            workflow.add_edge("load_context", "gen_basic_tests")
            workflow.add_edge("gen_basic_tests", "run_basic_generator")
            if mode == "basic":
                workflow.add_edge("run_basic_generator", END)
        
        if mode == "edge" or mode == "all":
            prev_node = "run_basic_generator" if mode == "all" else "load_context"
            workflow.add_edge(prev_node, "gen_edge_tests")
            workflow.add_edge("gen_edge_tests", "run_edge_generator")
            if mode == "edge":
                workflow.add_edge("run_edge_generator", END)
        
        if mode == "validator" or mode == "all":
            prev_node = "run_edge_generator" if mode == "all" else "load_context"
            workflow.add_edge(prev_node, "gen_validator")
            workflow.add_edge("gen_validator", END)
    
    return workflow.compile()

def main():
    """Parse command line arguments and run the workflow."""

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(
        description="Generate test cases and validator for a programming problem",
        epilog="""
Examples:
  # Generate basic test cases
  python 05_test_generator.py problem_dir --mode basic
  
  # Execute existing basic generator without regenerating
  python 05_test_generator.py problem_dir --mode basic --exec-only
  
  # Execute all existing generators without regenerating
  python 05_test_generator.py problem_dir --mode all --exec-only
  
  # Generate edge cases and execute them
  python 05_test_generator.py problem_dir --mode edge
        """
    )
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to the problem directory (default: {default_dir})")
    
    # Replace skip flags with mode selection
    parser.add_argument("--mode", type=str, default="all",
                        choices=["basic", "edge", "validator", "all"],
                        help="Generation mode: basic (50 tests), edge (5-10 edge cases), "
                             "validator (test case validator), or all (run all modes)")
    
    # Add exec-only flag that can be combined with any mode
    parser.add_argument("--exec-only", action="store_true",
                        help="Only execute existing generators without generating new ones (can be combined with --mode)")

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
    
    # Load language setting from global settings
    settings = get_settings()
    language = settings.get("language", "C++")
    logger.info(f"Using language: {language}")
    
    # If exec-only mode is enabled, check that required generators exist
    if args.exec_only:
        missing_generators = []
        file_ext = "cpp" if language == "C++" else "py"
        
        basic_gen_path = problem_paths.get_test_generator_path(language)
        edge_gen_path = problem_paths.get_edge_generator_path(language)
        
        if args.mode in ["basic", "all"] and not basic_gen_path.exists():
            missing_generators.append(f"test_generator.{file_ext}")
        if args.mode in ["edge", "all"] and not edge_gen_path.exists():
            missing_generators.append(f"edge_generator.{file_ext}")
        
        if missing_generators:
            logger.error("Error: --exec-only mode requested but the following generators are missing:")
            for generator in missing_generators:
                logger.error("  - %s", generator)
            logger.error("Please generate the missing generators first or remove the --exec-only flag.")
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
        "llm": llm,
        "generated_test_cases": None,
        "language": language
    }

    # Run the workflow
    graph = build_test_generator_graph(mode=args.mode, exec_only=args.exec_only)
    
    try:
        final_state = graph.invoke(initial_state)
        logger.info("--- Workflow Finished ---")
        
        # Report status based on mode and exec_only flag
        if args.exec_only:
            logger.info("✓ Executed existing generators in exec-only mode")
        else:
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
        
        # Report test case generation status
        generated_cases = final_state.get("generated_test_cases", {})
        if generated_cases:
            total_cases = sum(len(cases) for cases in generated_cases.values())
            logger.info("=" * 60)
            logger.info("🎉 TEST CASE GENERATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            logger.info("✓ Generated %d test cases total", total_cases)
            for category, cases in generated_cases.items():
                logger.info("  - %s: %d test cases", category, len(cases))
            logger.info("=" * 60)
        else:
            logger.warning("No test cases were generated")
        
        # Check if any requested component failed (only for non-exec-only modes)
        if not args.exec_only:
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