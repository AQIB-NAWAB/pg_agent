import re
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Any, TypedDict, Optional, Literal, Dict
from langchain_core.prompts import ChatPromptTemplate
from ..utils.structure import get_problem_paths
from ..utils.prompts import get_prompt_path, get_refinement_prompt_path
from ..pipeline.sandbox.sandbox_utils import run_generator_script

logger = logging.getLogger(__name__)

class TestCaseGeneratorState(TypedDict):
    """
    Represents the state for the Test Case Generation workflow.
    """
    problem_dir_path: str
    problem_statement: str
    bruteforce_code: Optional[str]  # Now optional
    basic_test_gen_path: Optional[str]
    edge_test_gen_path: Optional[str]
    validator_path: Optional[str]
    final_verdict: str
    refine_mode: bool  # Whether to refine existing generator
    user_feedback: str  # User feedback for refinement
    generation_mode: Literal["basic", "edge", "validator", "all"]  # The generation mode to use
    llm: Any  # LLM client injected from workflow
    generated_test_cases: Optional[Dict[str, list]]  # Paths to generated test case files
    
def _extract_cpp_code(response_content: str) -> str:
    """Parses the LLM's response to extract only the C++ code."""
    match = re.search(r'```(?:cpp)?\s*([\s\S]+?)\s*```', response_content)
    if match: return match.group(1).strip()
    return response_content.strip()

def load_context_node(state: TestCaseGeneratorState) -> dict:
    """Loads the problem statement and bruteforce solution if available.
    
    Only attempts to load bruteforce solution for test generators (basic/edge).
    For validator-only runs, or when not refining, only loads problem statement.
    """
    logger.info("Loading context from: %s", state['problem_dir_path'])
    paths = get_problem_paths(state['problem_dir_path'])
    
    # Always load problem statement
    if not paths.problem_statement.exists():
        raise FileNotFoundError(f"Problem statement not found at {paths.problem_statement}")
    problem_statement = paths.problem_statement.read_text(encoding="utf-8")
    logger.info("Loaded problem statement")
    
    # Try to load bruteforce solution if we're generating tests
    bruteforce_code = None
    if state["generation_mode"] in ["basic", "edge", "all"]:
        if paths.bruteforce_solution.exists():
            bruteforce_code = paths.bruteforce_solution.read_text(encoding="utf-8")
            logger.info("Loaded bruteforce solution from %s", paths.bruteforce_solution)
        else:
            logger.info("No bruteforce solution found at %s", paths.bruteforce_solution)
    
    return {
        "problem_statement": problem_statement,
        "bruteforce_code": bruteforce_code
    }

def _create_generation_node(prompt_file_name: str, output_key: str, version_key: str, needs_bruteforce: bool = True):
    """A factory to create a node that generates test case generator scripts."""
    def generation_node(state: TestCaseGeneratorState) -> dict:
        logger.info("Generating: %s", output_key)
        
        # Load settings using ProblemPaths
        paths = get_problem_paths(state['problem_dir_path'])
        settings = paths.get_settings()
        current_version = settings.get(version_key, -1)
        
        # If in refine mode, load existing code
        existing_code = None
        if state["refine_mode"] and current_version >= 0:
            file_prefix = paths.get_script_type_from_version_key(version_key)
            existing_path = paths.get_testcase_gen_script_path(file_prefix, current_version)
            if existing_path.exists():
                existing_code = existing_path.read_text(encoding="utf-8")
                logger.info("Loaded existing version %d for refinement", current_version)
            else:
                logger.warning("Could not find existing version %d for refinement", current_version)
        
        # Determine which prompt to use based on mode
        if state["refine_mode"] and existing_code:
            # Use refinement prompt if available
            refinement_prompt_path = get_refinement_prompt_path(prompt_file_name)
            if refinement_prompt_path:
                prompt_path = refinement_prompt_path
                logger.info("Using refinement prompt: %s", refinement_prompt_path.name)
            else:
                prompt_path = get_prompt_path(prompt_file_name)  # Fallback to regular prompt
                logger.warning("Refinement prompt not found, using regular prompt: %s", prompt_file_name)
        else:
            prompt_path = get_prompt_path(prompt_file_name)
            
        # Prepare prompt and invoke LLM
        prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
        llm = state["llm"]
        chain = prompt | llm
        
        # Include existing code and feedback in prompt if refining
        variables = {
            "problem_statement": state["problem_statement"],
            "bruteforce_code_section": ""
        }
        
        # Add bruteforce code section if available
        if state["bruteforce_code"]:
            variables["bruteforce_code_section"] = "\n**Provided Bruteforce Solution (for analysis):**\n```cpp\n" + state["bruteforce_code"] + "\n```"
        
        if state["refine_mode"] and existing_code:
            variables["existing_code"] = existing_code
            variables["user_feedback"] = state["user_feedback"]
            
        response = chain.invoke(variables)
        code = _extract_cpp_code(response.content)
        
        # Save the generated code to both automation directory (versioned) and root directory (latest)
        new_version = current_version + 1 if current_version >= 0 else 0
        file_prefix = paths.get_script_type_from_version_key(version_key)
        
        try:
            # Ensure automation directory exists
            paths.testcase_gen_script_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to automation directory with version
            automation_path = paths.get_testcase_gen_script_path(file_prefix, new_version)
            automation_path.write_text(code, encoding="utf-8")
            
            # Save to root directory with standard name
            root_path = paths.get_root_generator_path(file_prefix)
            if root_path:
                root_path.write_text(code, encoding="utf-8")
                logger.info("Saved to problem root: %s", root_path)
            else:
                logger.warning("Unknown generator type: %s", file_prefix)
            
            # Update settings with new version
            settings[version_key] = new_version
            paths.update_settings(settings)
            
            action = "Refined" if state["refine_mode"] and existing_code else "Created"
            logger.info("%s version %d at: %s", action, new_version, automation_path)
            
            return {output_key: str(automation_path)}
            
        except Exception as e:
            logger.error("Failed to save generated file: %s", e)
            raise

    return generation_node

def _run_generator_in_docker(generator_path: Path, output_dir: Path, generator_name: str) -> tuple[bool, list]:
    """Runs a test case generator in Docker using the existing sandbox utilities.
    
    Args:
        generator_path: Path to the C++ generator file
        output_dir: Directory to save generated test cases
        generator_name: Name of the generator for logging
        
    Returns:
        Tuple of (success, list_of_generated_files)
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a temporary directory for this run
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test_cases subdirectory in temp directory (as expected by generators)
        temp_test_cases = temp_path / "test_cases"
        temp_test_cases.mkdir(parents=True, exist_ok=True)
        
        logger.info("Running %s in Docker container...", generator_name)
        run_generator_script(str(generator_path), temp_path)
        
        # Check if test cases were generated in the test_cases subdirectory
        generated_files = list(temp_test_cases.glob("*.in"))
        if not generated_files:
            logger.warning("No .in files generated by %s", generator_name)
            return False, []
        
        # Copy generated test cases to output directory
        for test_file in generated_files:
            shutil.copy2(test_file, output_dir / test_file.name)
            logger.info("Copied test case: %s", test_file.name)
        
        logger.info("Successfully generated %d test cases from %s", len(generated_files), generator_name)
        return True, [str(f) for f in generated_files]

def run_test_generator_node(generator_type: str, generator_path: Path, state: TestCaseGeneratorState) -> dict:
    """Unified function to run any test generator in Docker and save test cases.
    
    Args:
        generator_type: Type of generator ("basic", "edge", or any custom type)
        generator_path: Path to the generator file
        state: Current workflow state
        
    Returns:
        Updated state with generated test cases
    """
    logger.info("Running %s test generator in Docker...", generator_type)
    
    # Check if generator exists
    if not generator_path.exists():
        logger.error("%s test generator not found at: %s", generator_type.title(), generator_path)
        if generator_type == "basic":
            return {"generated_test_cases": None}
        else:
            return {"generated_test_cases": state.get("generated_test_cases", {})}
    
    # Create test_cases directory
    test_cases_dir = get_problem_paths(state['problem_dir_path']).test_cases
    test_cases_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the generator
    success, generated_files = _run_generator_in_docker(
        generator_path, 
        test_cases_dir, 
        f"{generator_type}_test_generator"
    )
    
    if success:
        if generator_type == "basic":
            # For basic generator, create new test cases dict
            result = {
                "generated_test_cases": {
                    "basic": generated_files
                }
            }
        else:
            # For edge generator, update existing test cases
            existing_cases = state.get("generated_test_cases", {})
            existing_cases["edge"] = generated_files
            result = {
                "generated_test_cases": existing_cases
            }
        
        logger.info("✓ %s test generator completed successfully!", generator_type.title())
        logger.info("  Generated %d test cases:", len(generated_files))
        for test_file in generated_files:
            logger.info("    - %s", Path(test_file).name)
        logger.info("  Test cases saved to: %s", test_cases_dir)
        
        return result
    else:
        logger.error("✗ %s test generator failed", generator_type.title())
        if generator_type == "basic":
            return {"generated_test_cases": {}}
        else:
            return {"generated_test_cases": state.get("generated_test_cases", {})}

def run_basic_test_generator_node(state: TestCaseGeneratorState) -> dict:
    """Runs the basic test generator in Docker and saves test cases."""
    paths = get_problem_paths(state['problem_dir_path'])
    return run_test_generator_node("basic", paths.test_generator, state)

def run_edge_test_generator_node(state: TestCaseGeneratorState) -> dict:
    """Runs the edge test generator in Docker and saves test cases."""
    paths = get_problem_paths(state['problem_dir_path'])
    return run_test_generator_node("edge", paths.edge_generator, state)

def run_custom_test_generator_node(generator_type: str, generator_path: Path, state: TestCaseGeneratorState) -> dict:
    """Runs a custom test generator in Docker and saves test cases.
    
    This function can be used for any type of test generator beyond basic and edge.
    
    Args:
        generator_type: Custom type name for the generator
        generator_path: Path to the generator file
        state: Current workflow state
        
    Returns:
        Updated state with generated test cases
    """
    return run_test_generator_node(generator_type, generator_path, state)

# Create the generator nodes
gen_basic_tests_node = _create_generation_node(
    "gen_basic_tests.txt", "basic_test_gen_path", "basicTestcaseGeneratorVersion", needs_bruteforce=True
)
gen_edge_tests_node = _create_generation_node(
    "gen_edge_tests.txt", "edge_test_gen_path", "edgeTestcaseGeneratorVersion", needs_bruteforce=True
)
gen_validator_node = _create_generation_node(
    "gen_validator.txt", "validator_path", "testcaseValidatorVersion", needs_bruteforce=False
) 
