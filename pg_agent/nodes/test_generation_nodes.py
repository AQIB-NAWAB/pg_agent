import os
import logging
from pathlib import Path
from typing import TypedDict, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from ..utils.parsing import parse_test_cases

logger = logging.getLogger(__name__)

class TestGenerationState(TypedDict):
    """State for test case generation workflow."""
    output_dir: str
    problem_statement: str
    test_cases: List[Tuple[str, str]]

def get_llm_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key: raise ValueError("OPENAI_API_KEY not found in environment.")
    return ChatOpenAI(model="o4-mini", api_key=api_key, max_tokens=8192)

def generate_test_cases(state: TestGenerationState) -> TestGenerationState:
    """Generate additional test cases beyond examples."""
    prompt_path = Path(__file__).parent.parent / "prompts/generate_examples.txt"
    prompt = ChatPromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    chain = prompt | get_llm_client()
    response = chain.invoke({"problem_statement": state["problem_statement"]})
    logger.info("Generated test cases from LLM")
    
    test_cases = parse_test_cases(response.content)
    logger.info("Parsed %d test cases", len(test_cases))

    # Save the test cases
    test_cases_dir = Path(state['output_dir']) / "test_cases"
    test_cases_dir.mkdir(exist_ok=True)
    # Clean up existing test files
    for f in test_cases_dir.glob("test_*.in"):
        f.unlink()
    for f in test_cases_dir.glob("test_*.out"):
        f.unlink()
    
    for i, (input_data, output_data) in enumerate(test_cases, 1):
        input_path = test_cases_dir / f"test_{i}.in"
        output_path = test_cases_dir / f"test_{i}.out"
        input_path.write_text(input_data, encoding="utf-8")
        output_path.write_text(output_data, encoding="utf-8")
        logger.debug("Saved test case %d to %s and %s", i, input_path, output_path)
    
    return {"test_cases": test_cases} 