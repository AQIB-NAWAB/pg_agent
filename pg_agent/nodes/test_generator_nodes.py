import os
import re
import json
import logging
from pathlib import Path
from typing import Any, TypedDict, Optional, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.structure import get_problem_paths

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
            file_prefix = version_key.replace("Version", "")
            existing_path = paths.automation / "testcaseGenScript" / f"{file_prefix}_v{current_version}.cpp"
            if existing_path.exists():
                existing_code = existing_path.read_text(encoding="utf-8")
                logger.info("Loaded existing version %d for refinement", current_version)
            else:
                logger.warning("Could not find existing version %d for refinement", current_version)
        
        # Determine which prompt to use based on mode
        if state["refine_mode"] and existing_code:
            # Use refinement prompt
            prompt_name = prompt_file_name.replace(".txt", "_refine.txt")
            if not (Path(__file__).parent.parent / "prompts" / prompt_name).exists():
                prompt_name = prompt_file_name  # Fallback to regular prompt
                logger.warning("Refinement prompt %s not found, using regular prompt", prompt_name)
        else:
            prompt_name = prompt_file_name
            
        # Prepare prompt and invoke LLM
        prompt_path = Path(__file__).parent.parent / "prompts" / prompt_name
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
        
        # Save the generated code in automation directory
        new_version = current_version + 1 if current_version >= 0 else 0
        script_dir = paths.automation / "testcaseGenScript"
        script_dir.mkdir(parents=True, exist_ok=True)
        
        file_prefix = version_key.replace("Version", "")
        final_path = script_dir / f"{file_prefix}_v{new_version}.cpp"
        final_path.write_text(code, encoding="utf-8")
        
        settings[version_key] = new_version
        paths.update_settings(settings)
        
        # Also save to problem root directory with appropriate name
        root_path = {
            "basicTestcaseGenerator": paths.test_generator,
            "edgeTestcaseGenerator": paths.edge_generator,
            "testcaseValidator": paths.validator
        }.get(file_prefix)
        
        if root_path:
            root_path.write_text(code, encoding="utf-8")
            logger.info("Copied generator to problem root: %s", root_path)
        else:
            logger.warning("Unknown generator type: %s", file_prefix)
        
        action = "Refined" if state["refine_mode"] and existing_code else "Created"
        logger.info("%s version %d at: %s", action, new_version, final_path)
        return {output_key: str(final_path)}

    return generation_node

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