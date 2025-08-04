import re
from typing import List, Tuple

def parse_test_cases(response: str) -> List[Tuple[str, str]]:
    """Parse test cases from a response string.
    
    Args:
        response: String containing test cases in XML format with <test_case>, <input>, and <output> tags
        
    Returns:
        List of tuples containing (input_string, output_string) for each test case
    """
    test_cases = []
    for match in re.finditer(r'<test_case>(.*?)</test_case>', response, re.DOTALL):
        block = match.group(1)
        input_match = re.search(r'<input>(.*?)</input>', block, re.DOTALL)
        output_match = re.search(r'<output>(.*?)</output>', block, re.DOTALL)
        if input_match and output_match:
            test_cases.append((input_match.group(1).strip(), output_match.group(1).strip()))
    return test_cases 

def extract_cpp_code(raw):
    """
    Extracts the last block of C++ code from a raw string, stripping out any Think tags or code block syntax.
    This assumes the last code block contains the final, complete solution after any analysis or iterations.

    Args:
        raw: A string that may contain C++ code blocks or think tags.

    Returns:
        The cleaned C++ code as a string.
    """
    
    # Remove any think tags first
    raw = re.sub(r"</?think.*?>", "", raw, flags=re.IGNORECASE | re.DOTALL)
    
    # Find all code blocks
    matches = re.findall(r"```(?:cpp|c\+\+)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip()
        
    # Fallback: if no code blocks found, clean up any stray backticks and return the whole text
    raw = re.sub(r"```+", "", raw)
    return raw.strip()
