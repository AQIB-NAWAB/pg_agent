import os
import logging
from pathlib import Path
from typing import TypedDict, Optional, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.parsing import parse_test_cases

logger = logging.getLogger(__name__)

class ProblemDefinitionState(TypedDict):
    """State for the problem definition workflow."""
    output_dir: str
    topics: Optional[str]
    user_prompt: Optional[str]
    human_feedback: Optional[str]
    previous_problem: Optional[str]
    problem_statement: str
    test_cases: List[Tuple[str, str]]

def get_llm_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o4-mini", api_key=api_key)

def generate_problem_statement(state: dict) -> dict:
    """Generate initial problem statement."""
    prompt_path = Path(__file__).parent.parent / "prompts/generate_problem.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    chain = prompt | get_llm_client()
    response = chain.invoke({
        "topics": state.get("topics") or "None",
        "previous_problem": state.get("previous_problem") or "None",
        "user_prompt": state.get("user_prompt") or "None",
    })
    
    # Save the problem statement
    problem_path = Path(state['output_dir']) / "problem_statement.md"
    problem_path.write_text(response.content, encoding="utf-8")
    
    return {"problem_statement": response.content}

def refine_problem_statement(state: dict) -> dict:
    """Refine problem statement based on feedback."""
    if not state.get("human_feedback"):
        logger.info("No human feedback provided, skipping refinement")
        return state
        
    logger.info("Refining problem statement based on human feedback")
    
    # If problem_statement is not in state, read it from file
    problem_statement = state.get("problem_statement")
    if not problem_statement:
        problem_path = Path(state['output_dir']) / "problem_statement.md"
        if problem_path.exists():
            problem_statement = problem_path.read_text(encoding="utf-8")
        else:
            raise ValueError("No problem statement found to refine. Make sure problem_statement.md exists in the output directory.")
    
    prompt_path = Path(__file__).parent.parent / "prompts/refine_problem.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    chain = prompt | get_llm_client()
    response = chain.invoke({
        "problem_statement": problem_statement,
        "human_feedback": state["human_feedback"],
    })
    
    # Save the refined problem statement
    problem_path = Path(state['output_dir']) / "problem_statement.md"
    problem_path.write_text(response.content, encoding="utf-8")
    logger.info("Saved refined problem statement to %s", problem_path)
    
    return {"problem_statement": response.content}

def extract_examples(state: dict) -> dict:
    """Extract and format example test cases from the problem statement."""
    logger.info("Starting test case extraction from problem statement")
    problem_statement = state["problem_statement"]
    
    # First run the formatting chain
    prompt_path = Path(__file__).parent.parent / "prompts/format_test_cases.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    chain = prompt | get_llm_client()
    response = chain.invoke({"problem_statement": problem_statement})
    
    # Then parse the formatted test cases
    test_cases = parse_test_cases(response.content)
    if not test_cases and response.content.strip():
        logger.warning("No test cases were parsed from non-empty LLM response. Response length: %d", len(response.content))
        logger.warning("First 200 characters of response: %s", response.content[:200])
    else:
        logger.info("Extracted %d test cases from problem statement", len(test_cases))

    # Save the test cases
    test_cases_dir = Path(state['output_dir']) / "test_cases"
    test_cases_dir.mkdir(exist_ok=True)
    for f in test_cases_dir.glob("example_*"):
        f.unlink()
    for i, (input_data, output_data) in enumerate(test_cases, 1):
        input_path = test_cases_dir / f"example_{i}.in"
        output_path = test_cases_dir / f"example_{i}.out"
        input_path.write_text(input_data, encoding="utf-8")
        output_path.write_text(output_data, encoding="utf-8")
        logger.info("Saved test case %d to %s and %s", i, input_path, output_path)
    
    return {"test_cases": test_cases} 