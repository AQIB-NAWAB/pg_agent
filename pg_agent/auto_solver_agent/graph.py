from langgraph.graph import StateGraph, END
from .schemas import SolverState
from .nodes import (
    gen_bruteforce_node,
    gen_test_case_code_node,
    run_test_case_generator_node,
    gen_optimal_solution_node,
    refine_solution_node,
    run_tests_node,
    cleanup_node,
)

# --- NEW: Decision node to check if test case generation was successful ---
def check_tests_generated(state: SolverState) -> str:
    """
    Checks if the test case generation step produced a valid directory path.
    If not, it routes to the end to prevent fatal errors.
    """
    print("--- Decision: Test Cases Generated Successfully? ---")
    if state.get("test_cases_dir_path"):
        print("  -> Yes, path found. Proceeding to generate optimal solution.")
        return "proceed"
    else:
        print("  -> No, path not found. A fatal error occurred during generation. Ending run.")
        # If the path wasn't created, something went wrong. End the graph.
        return "end"

def should_refine(state: SolverState) -> str:
    """Decision node: determines if we should loop to refine or finish."""
    print("--- Decision: Should Refine? ---")
    if state["test_results"]["failed"] == 0:
        print("  -> Verdict: PASSED. Proceed to cleanup.")
        return "cleanup"
    
    if state["iteration_count"] >= state["max_iterations"]:
        print(f"  -> Verdict: FAILED. Max iterations ({state['max_iterations']}) reached.")
<<<<<<< HEAD
        return "cleanup"
=======
        return "cleanup" # Go to cleanup even on failure
>>>>>>> 3d60c04 (auto agent basic flow)
    
    print(f"  -> Verdict: FAILED. Continuing to refinement loop (Attempt #{state['iteration_count'] + 1}).")
    return "refine_solution"

def build_auto_solver_graph():
<<<<<<< HEAD
    """Builds the LangGraph agent with a robust sequential flow."""
    workflow = StateGraph(SolverState)

    # Add all the nodes to the graph
    workflow.add_node("gen_bruteforce", gen_bruteforce_node)
    workflow.add_node("gen_test_case_code", gen_test_case_code_node)
    workflow.add_edge("gen_bruteforce", "gen_test_case_code")
    workflow.add_node("run_test_case_generator", run_test_case_generator_node)
=======
    """Builds the LangGraph agent for solving programming problems."""
    workflow = StateGraph(SolverState)

    workflow.add_node("gen_bruteforce", gen_bruteforce_node)
    # This node now generates the code AND runs it to create the test case files
    workflow.add_node("gen_tests", gen_and_run_test_cases_node)
>>>>>>> 3d60c04 (auto agent basic flow)
    workflow.add_node("gen_optimal", gen_optimal_solution_node)
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("refine_solution", refine_solution_node)
    workflow.add_node("cleanup", cleanup_node)

<<<<<<< HEAD
    # --- Define the Correct Sequential Flow ---
    
    # 1. Start by generating the bruteforce solution.
    workflow.set_entry_point("gen_bruteforce")
    
    # 2. Sequentially generate the necessary code.
    workflow.add_edge("gen_bruteforce", "gen_test_case_code")
    workflow.add_edge("gen_test_case_code", "run_test_case_generator")

    # 3. After running the generator, check if it was successful.
    workflow.add_conditional_edges(
        "run_test_case_generator",
        check_tests_generated,
        {
            "proceed": "gen_optimal", # If successful, continue to the next step
            "end": "cleanup",         # If it failed, go directly to cleanup
        }
    )

    # 4. Generate the optimal solution, then run the main tests.
    workflow.add_edge("gen_optimal", "run_tests")

    # 5. The refinement loop logic remains the same.
=======
    # The entry point forks to three parallel generation nodes
    workflow.set_entry_point("gen_bruteforce")
    workflow.add_edge("gen_bruteforce", "gen_tests")
    workflow.add_edge("gen_tests", "gen_optimal")
    
    # After the optimal solution is generated, we proceed to the first test run.
    workflow.add_edge("gen_optimal", "run_tests")

    # After running tests, we make a decision
>>>>>>> 3d60c04 (auto agent basic flow)
    workflow.add_conditional_edges(
        "run_tests",
        should_refine,
        {
            "refine_solution": "refine_solution",
            "cleanup": "cleanup",
        },
    )
<<<<<<< HEAD
    workflow.add_edge("refine_solution", "run_tests")
    
    # 6. The cleanup node is the end of the graph.
=======

    workflow.add_edge("refine_solution", "run_tests")
>>>>>>> 3d60c04 (auto agent basic flow)
    workflow.add_edge("cleanup", END)

    return workflow.compile()

auto_solver_graph = build_auto_solver_graph()