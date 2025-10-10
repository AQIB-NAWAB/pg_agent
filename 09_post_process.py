#!/usr/bin/env python3
"""
Post-process Jupyter notebooks to extract metadata, problem statements, solutions, and standard code.

This script extracts data from Jupyter notebooks (typically from Colab) and processes them
to create structured problem directories with metadata, problem statements, solutions, and standard code.

Usage:
    python 09_post_process.py [problem_dir] [options]
    python 09_post_process.py --nbook notebook.ipynb [options]

Examples:
    # Process all extractions for default problem directory
    python 09_post_process.py

    # Process specific notebook file
    python 09_post_process.py --nbook my_notebook.ipynb

    # Extract only metadata and problem statement
    python 09_post_process.py --extract-meta --extract-problem

    # Extract solution and standard code for Python
    python 09_post_process.py --extract-solution --extract-standard --language Python
"""

import os
import sys
import json
import argparse
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.env import get_settings

def find_notebook_in_problem_dir(problem_dir: Path) -> Optional[Path]:
    """Find Jupyter notebook in problem directory."""
    # Common notebook patterns
    notebook_patterns = [
        "*.ipynb",
        "*_colab.ipynb", 
        "*_notebook.ipynb",
        "notebook.ipynb",
        "colab.ipynb"
    ]
    
    for pattern in notebook_patterns:
        notebooks = list(problem_dir.glob(pattern))
        if notebooks:
            # Return the first (most likely) notebook
            return notebooks[0]
    
    return None


def parse_metadata_from_notebook(notebook_path: Path, logger: logging.Logger) -> Dict:
    """Parse metadata from the Jupyter notebook's Metadata cell."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Find the Metadata cell (usually the first cell with "# Metadata" or "**Metadata**")
        metadata_cell = None
        for cell in notebook.get('cells', []):
            if cell.get('cell_type') == 'markdown':
                source = cell.get('source', [])
                if isinstance(source, list):
                    cell_text = ''.join(source)
                else:
                    cell_text = str(source)
                
                if cell_text.strip().startswith('**Metadata**') or cell_text.strip().startswith('# Metadata'):
                    metadata_cell = cell_text
                    break
        
        if not metadata_cell:
            logger.warning(f"No Metadata cell found in {notebook_path.name}")
            return {}
        
        # Parse the metadata
        metadata = {}
        lines = metadata_cell.split('\n')
        
        for line in lines:
            line = line.strip()
            if '**' in line and ':' in line:
                # Extract field name and value
                parts = line.split(':', 1)
                if len(parts) == 2:
                    field_name = parts[0].replace('**', '').strip().lower()
                    field_value = parts[1].strip()
                    
                    # Remove any remaining ** markers and leading dashes
                    field_value = field_value.replace('**', '').strip()
                    if field_value.startswith('- '):
                        field_value = field_value[2:]
                    
                    # Parse specific fields
                    if field_name == 'category':
                        metadata['category'] = field_value
                    elif field_name == 'topic':
                        metadata['topic'] = field_value
                    elif field_name == 'subtopic':
                        # Parse JSON array from string
                        try:
                            if field_value.startswith("['") and field_value.endswith("']"):
                                json_value = field_value.replace("'", '"')
                                subtopics = json.loads(json_value)
                                metadata['subtopic'] = subtopics
                            elif field_value.startswith("- ['") and field_value.endswith("']"):
                                inner_value = field_value[2:]
                                json_value = inner_value.replace("'", '"')
                                subtopics = json.loads(json_value)
                                metadata['subtopic'] = subtopics
                            elif field_value.startswith('[') and field_value.endswith(']'):
                                subtopics = json.loads(field_value)
                                metadata['subtopic'] = subtopics
                            else:
                                metadata['subtopic'] = [field_value]
                        except json.JSONDecodeError:
                            metadata['subtopic'] = [field_value]
                    elif field_name == 'difficulty':
                        metadata['difficulty'] = field_value
                    elif field_name == 'languages':
                        metadata['language'] = field_value
                    elif field_name == 'number of approaches':
                        # Handle different formats for approaches
                        if isinstance(field_value, list):
                            approaches = field_value
                        elif isinstance(field_value, str):
                            if '->' in field_value or ' to ' in field_value or r'\rightarrow' in field_value:
                                if '->' in field_value:
                                    approaches = [app.strip() for app in field_value.split('->')]
                                elif ' to ' in field_value:
                                    approaches = [app.strip() for app in field_value.split(' to ')]
                                elif r'\\rightarrow' in field_value:
                                    approaches = [app.strip() for app in field_value.split(r'\\rightarrow')]
                                elif r'\rightarrow' in field_value:
                                    approaches = [app.strip() for app in field_value.split(r'\rightarrow')]
                                else:
                                    approaches = [app.strip() for app in field_value.split(r'\to')]
                                
                                if approaches and ',' in approaches[0]:
                                    first_part = approaches[0].split(',', 1)
                                    if first_part[0].strip().isdigit():
                                        approaches[0] = int(first_part[0].strip())
                                        approaches.insert(1, first_part[1].strip())
                                elif approaches and approaches[0].isdigit():
                                    approaches[0] = int(approaches[0])
                            else:
                                approaches = [app.strip() for app in field_value.split(',')]
                                if approaches and approaches[0].isdigit():
                                    approaches[0] = int(approaches[0])
                        else:
                            approaches = [str(field_value)]
                        
                        # Format approaches with proper LaTeX formatting (same as delivery_gen.py)
                        if isinstance(approaches, list) and len(approaches) > 1:
                            formatted_approaches = [approaches[0]]  # Keep the first element (number) as-is
                            
                            for i, approach in enumerate(approaches[1:], 1):
                                if not isinstance(approach, str):
                                    logger.warning(f"Approach {i} is not a string, converting to string")
                                    approach = str(approach)
                                
                                # Ensure proper LaTeX formatting with $ symbols
                                formatted_approach = approach.strip()
                                
                                # Count the number of $ symbols
                                dollar_count = formatted_approach.count('$')
                                
                                # If there's an even number of $ symbols and not zero, don't add any
                                if dollar_count > 0 and dollar_count % 2 == 0:
                                    # Already properly formatted with even number of $ symbols
                                    logger.debug(f"Approach {i} already has proper $ formatting")
                                else:
                                    # Add $ symbols if needed
                                    if not formatted_approach.startswith('$'):
                                        formatted_approach = '$' + formatted_approach
                                    if not formatted_approach.endswith('$'):
                                        formatted_approach = formatted_approach + '$'
                                    logger.debug(f"Added $ formatting to approach {i}")
                                
                                formatted_approaches.append(formatted_approach)
                            
                            metadata['number of approaches'] = formatted_approaches
                        else:
                            metadata['number of approaches'] = approaches

        
        logger.debug(f"Parsed metadata: {list(metadata.keys())}")
        return metadata
        
    except Exception as e:
        logger.error(f"Error parsing metadata from {notebook_path.name}: {e}")
        return {}


def extract_prompt_from_notebook(notebook_path: Path, logger: logging.Logger) -> str:
    """Extract the [Prompt] cell content from the Jupyter notebook."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Find the [Prompt] cell
        prompt_cell = None
        prompt_cell_type = None
        
        for cell in notebook.get('cells', []):
            if cell.get('cell_type') == 'markdown':
                source = cell.get('source', [])
                if isinstance(source, list):
                    cell_text = ''.join(source)
                else:
                    cell_text = str(source)
                
                if cell_text.strip().startswith('**[Prompt]**'):
                    prompt_cell = cell_text
                    prompt_cell_type = 'prompt'
                    break
        
        # If no [Prompt] cell found, try alternative patterns
        if not prompt_cell:
            # Look for cells with Time limit or title pattern
            for cell in notebook.get('cells', []):
                if cell.get('cell_type') == 'markdown':
                    source = cell.get('source', [])
                    if isinstance(source, list):
                        cell_text = ''.join(source)
                    else:
                        cell_text = str(source)
                    
                    # Check for Time limit pattern
                    if re.search(r'(?:\*\*)?Time [Ll]imit:(?:\*\*)?', cell_text):
                        prompt_cell = cell_text
                        prompt_cell_type = 'time_limit'
                        break
        
        if not prompt_cell:
            logger.warning(f"No [Prompt] cell found in {notebook_path.name}")
            return ""
        
        # Process the cell based on its type
        if prompt_cell_type == 'prompt':
            # Remove the **[Prompt]** header and next empty line
            lines = prompt_cell.split('\n')
            prompt_lines = []
            skip_next_empty = False
            
            for line in lines:
                if line.strip() == '**[Prompt]**':
                    skip_next_empty = True
                    continue
                elif skip_next_empty and line.strip() == '':
                    skip_next_empty = False
                    continue
                else:
                    prompt_lines.append(line)
            
            prompt_content = '\n'.join(prompt_lines).strip()
        else:
            # For time_limit or title patterns, use the cell content as-is
            prompt_content = prompt_cell.strip()
        
        logger.debug(f"Extracted prompt content ({len(prompt_content)} characters) using {prompt_cell_type} pattern")
        return prompt_content
        
    except Exception as e:
        logger.error(f"Error extracting prompt from {notebook_path.name}: {e}")
        return ""


def extract_solution_from_notebook(notebook_path: Path, logger: logging.Logger) -> str:
    """Extract solution content from the Jupyter notebook starting from [CHAIN_01]."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        
        # Find cells starting from [CHAIN_01]
        solution_cells = []
        found_chain_start = False
        
        for cell in notebook.get('cells', []):
            if cell.get('cell_type') == 'markdown':
                source = cell.get('source', [])
                if isinstance(source, list):
                    cell_text = ''.join(source)
                else:
                    cell_text = str(source)
                
                # Check if this cell starts with [CHAIN_01]
                if cell_text.strip().startswith('**[CHAIN_01]**'):
                    found_chain_start = True
                
                # If we've found the start, collect all subsequent cells
                if found_chain_start:
                    # Skip cells that contain only delimiters (like ---)
                    cell_content = cell_text.strip()
                    if cell_content and not all(c in '-=*' for c in cell_content.replace(' ', '')):
                        # Remove trailing --- from the cell content
                        cleaned_cell = cell_text.rstrip().rstrip('-').rstrip()
                        solution_cells.append(cleaned_cell)
        
        if not solution_cells:
            logger.warning(f"No solution cells found starting from [CHAIN_01] in {notebook_path.name}")
            return ""
        
        # Concatenate all solution cells
        solution_content = '\n\n'.join(solution_cells)
        
        logger.debug(f"Extracted solution content ({len(solution_content)} characters) from {len(solution_cells)} cells")
        return solution_content
        
    except Exception as e:
        logger.error(f"Error extracting solution from {notebook_path.name}: {e}")
        return ""


def extract_standard_from_solution(solution_path: Path, language: str = "C++", logger: logging.Logger = None) -> bool:
    """Extract the last code block from solution.md and save it to standard.{ext}."""
    if logger is None:
        logger = logging.getLogger(__name__)
    
    try:
        if not solution_path.exists():
            logger.error(f"solution.md not found at {solution_path}")
            return False
        
        with open(solution_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Determine file extension based on language
        file_ext = "cpp" if language == "C++" else "py"
        
        # Find all code blocks (```cpp, ```c++, ```python, ```py, or ```)
        code_blocks = []
        lines = content.split('\n')
        in_code_block = False
        current_block = []
        current_language = None
        
        for line in lines:
            if line.strip().startswith('```'):
                if in_code_block:
                    # End of previous block, save it
                    if current_language and current_block:
                        code_blocks.append((current_language, '\n'.join(current_block)))
                in_code_block = True
                current_block = []
                # Extract language from code block marker
                marker = line.strip()
                if marker == '```':
                    current_language = None
                else:
                    current_language = marker[3:].strip()
            elif in_code_block:
                current_block.append(line)
        
        if not code_blocks:
            logger.error(f"No code blocks found in solution.md")
            return False
        
        # Find the last code block that matches our language
        matching_blocks = []
        for lang, block in code_blocks:
            if (language == "C++" and lang in ['cpp', 'c++', None]) or \
               (language == "Python" and lang in ['python', 'py', None]):
                matching_blocks.append(block)
        
        if not matching_blocks:
            logger.error(f"No {language} code blocks found in solution.md")
            return False
        
        # Get the last matching code block
        last_code_block = matching_blocks[-1]
        
        # Save to standard.{ext}
        standard_path = solution_path.parent / f"standard.{file_ext}"
        with open(standard_path, 'w', encoding='utf-8') as f:
            f.write(last_code_block)
        
        logger.debug(f"Extracted last {language} code block to standard.{file_ext} ({len(last_code_block)} characters)")
        return True
        
    except Exception as e:
        logger.error(f"Error extracting standard.{file_ext} from solution.md: {e}")
        return False


def extract_examples_from_test_cases(problem_dir: Path, logger: logging.Logger) -> List[Dict]:
    """Extract examples from test_cases/example_N.in/out files."""
    examples = []
    test_cases_dir = problem_dir / 'test_cases'
    
    if not test_cases_dir.exists():
        logger.debug(f"No test_cases directory found in {problem_dir.name}")
        return examples
    
    # Find all example_N.in files
    example_files = sorted(test_cases_dir.glob('example_*.in'))
    
    for example_file in example_files:
        # Extract the example number from filename
        match = re.match(r'example_(\d+)\.in', example_file.name)
        if not match:
            continue
        
        example_num = match.group(1)
        output_file = test_cases_dir / f'example_{example_num}.out'
        
        if output_file.exists():
            try:
                with open(example_file, 'r', encoding='utf-8') as f:
                    input_content = f.read().strip()
                
                with open(output_file, 'r', encoding='utf-8') as f:
                    output_content = f.read().strip()
                
                examples.append({
                    "input": input_content,
                    "output": output_content
                })
                
                logger.debug(f"Extracted example {example_num} from test_cases")
                
            except Exception as e:
                logger.warning(f"Error reading example {example_num}: {e}")
        else:
            logger.debug(f"Output file not found for example {example_num}: {output_file}")
    
    if examples:
        logger.debug(f"Extracted {len(examples)} examples from test_cases")
    else:
        logger.debug(f"No examples found in test_cases directory")
    
    return examples


def update_metadata_json(problem_dir: Path, notebook_metadata: Dict, logger: logging.Logger) -> bool:
    """Update metadata.json with parsed notebook metadata and requirements data."""
    try:
        metadata_path = problem_dir / 'metadata.json'
        requirements_path = problem_dir / 'requirements.json'
        
        # Start with existing metadata.json if it exists
        metadata = {}
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                logger.debug(f"Loaded existing metadata.json for {problem_dir.name}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in existing metadata.json: {e}, starting fresh")
                metadata = {}
        else:
            logger.debug(f"No existing metadata.json found for {problem_dir.name}, creating new one")
        
        # Update with notebook metadata (these take precedence over existing values)
        if 'category' in notebook_metadata:
            metadata['category'] = notebook_metadata['category']
        if 'topic' in notebook_metadata:
            metadata['topic'] = notebook_metadata['topic']
        if 'subtopic' in notebook_metadata:
            metadata['subtopic'] = notebook_metadata['subtopic']
        if 'difficulty' in notebook_metadata:
            metadata['difficulty'] = notebook_metadata['difficulty']
        if 'language' in notebook_metadata:
            metadata['language'] = notebook_metadata['language']
        if 'number of approaches' in notebook_metadata:
            metadata['number of approaches'] = notebook_metadata['number of approaches']
        
        # Update with requirements metadata (time and space) if available
        if requirements_path.exists():
            try:
                with open(requirements_path, 'r', encoding='utf-8') as f:
                    requirements = json.load(f)
                
                # Update with requirements data
                if 'time' in requirements:
                    metadata['time'] = requirements['time']
                if 'space' in requirements:
                    metadata['space'] = requirements['space']
                if 'title' in requirements:
                    metadata['title'] = requirements['title']
                if 'description' in requirements:
                    metadata['description'] = requirements['description']
                
                logger.debug(f"Updated metadata with requirements.json data for {problem_dir.name}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in requirements.json: {e}")
            except Exception as e:
                logger.warning(f"Error reading requirements.json: {e}")
        else:
            logger.debug(f"requirements.json not found in {problem_dir}")
        
        # Extract examples from test_cases
        examples = extract_examples_from_test_cases(problem_dir, logger)
        if examples:
            metadata['examples'] = examples
        
        # Create ordered metadata with title first
        ordered_metadata = {}
        
        # Add title first if it exists
        if 'title' in metadata:
            ordered_metadata['title'] = metadata['title']
        
        # Add other fields in the desired order
        field_order = [
            'category', 'topic', 'subtopic', 'difficulty', 'language',
            'number of approaches', 'time', 'space',
            'examples'
        ]
        
        for field in field_order:
            if field in metadata:
                ordered_metadata[field] = metadata[field]
        
        # Add any remaining fields that weren't in the ordered list
        for key, value in metadata.items():
            if key not in ordered_metadata:
                ordered_metadata[key] = value
        
        # Write updated metadata.json
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(ordered_metadata, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Updated metadata.json for {problem_dir.name}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating metadata.json for {problem_dir.name}: {e}")
        return False


def save_prompt_to_problem_statement(problem_dir: Path, prompt_content: str, logger: logging.Logger) -> bool:
    """Save the extracted prompt content to problem_statement.md."""
    try:
        if not prompt_content:
            logger.warning(f"No prompt content to save for {problem_dir.name}")
            return False
        
        problem_statement_path = problem_dir / 'problem_statement.md'
        
        # Remove **[Prompt]** header if found at the beginning
        prompt_content = re.sub(r'^\s*\*\*\[Prompt\]\*\*\s*\n?', '', prompt_content, flags=re.MULTILINE)
        
        # 1. Get problem title from problem_title.md/txt
        problem_title_path = problem_dir / 'problem_title.txt'
        if not problem_title_path.exists():
            problem_title_path = problem_dir / 'problem_title.md'
        
        file_title = None
        if problem_title_path.exists():
            try:
                with open(problem_title_path, 'r', encoding='utf-8') as f:
                    file_title = f.read().strip()
                    # Remove any existing # from the title
                    if file_title.startswith('#'):
                        file_title = file_title.lstrip('#').strip()
            except Exception as e:
                logger.warning(f"Could not read {problem_title_path.name} for {problem_dir.name}: {e}")
        
        # 2. Check that time limit and space limit are specified
        time_limit_match = re.search(r'(?:\*\*)?Time [Ll]imit:(?:\*\*)?', prompt_content)
        space_limit_match = re.search(r'(?:\*\*)?Memory [Ll]imit:(?:\*\*)?', prompt_content)
        
        if not time_limit_match:
            logger.warning(f"Time limit not found in prompt content for {problem_dir.name}")
        if not space_limit_match:
            logger.warning(f"Memory limit not found in prompt content for {problem_dir.name}")
        
        # 3. Check title formatting and consistency
        if time_limit_match:
            # Get content before and after time limit
            title_content = prompt_content[:time_limit_match.start()].strip()
            content_after_title = prompt_content[time_limit_match.start():]
        else:
            # No time limit found, search first few lines for title
            lines = prompt_content.split('\n')[:5]  # Check first 5 lines
            title_content = ""
            content_after_title = prompt_content
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith('#'):
                    title_content = line
                    content_after_title = '\n'.join(lines[i+1:]) + '\n' + '\n'.join(prompt_content.split('\n')[5:])
                    break
                elif line.startswith('**') and line.endswith('**'):
                    title_content = line
                    content_after_title = '\n'.join(lines[i+1:]) + '\n' + '\n'.join(prompt_content.split('\n')[5:])
                    break
        
        # Check if title is properly formatted with # and matches file title
        if file_title and title_content:
            # Look for # title pattern in title content
            title_match = re.search(r'^#\s*(.+)$', title_content, re.MULTILINE)
            if title_match:
                notebook_title = title_match.group(1).strip()
                if notebook_title != file_title:
                    logger.warning(f"Title mismatch for {problem_dir.name}: notebook has '{notebook_title}' but file has '{file_title}'")
            else:
                # Check for **title** pattern and warn about formatting
                title_match = re.search(r'\*\*([^*]+?)\*\*', title_content)
                if title_match:
                    notebook_title = title_match.group(1).strip()
                    if notebook_title == file_title:
                        logger.warning(f"Title found but incorrectly formatted with ** for {problem_dir.name}, should use # format")
                    else:
                        logger.warning(f"Title mismatch and incorrect formatting for {problem_dir.name}: notebook has '{notebook_title}' but file has '{file_title}'")
                else:
                    logger.warning(f"No title found in content for {problem_dir.name}, expected '{file_title}'")
        elif file_title and not title_content:
            logger.warning(f"No title found in content for {problem_dir.name}, expected '{file_title}'")
        
        # 4. Format the final content with proper title
        if file_title:
            # Ensure title is properly formatted with # and has empty line after
            formatted_content = f"# {file_title}\n\n{content_after_title}"
        else:
            # No file title, use content as-is
            formatted_content = content_after_title
        
        # Write the formatted prompt content to problem_statement.md
        with open(problem_statement_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        
        logger.debug(f"Updated problem_statement.md for {problem_dir.name}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving problem_statement.md for {problem_dir.name}: {e}")
        return False


def save_solution_to_file(problem_dir: Path, solution_content: str, logger: logging.Logger) -> bool:
    """Save the extracted solution content to solution.md."""
    try:
        if not solution_content:
            logger.warning(f"No solution content to save for {problem_dir.name}")
            return False
        
        solution_path = problem_dir / 'solution.md'
        
        # Add [COT] header and newline at the beginning
        full_content = "**[COT]**\n\n" + solution_content
        
        # Write the solution content to solution.md
        with open(solution_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        logger.debug(f"Updated solution.md for {problem_dir.name}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving solution.md for {problem_dir.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Post-process Jupyter notebooks to extract structured data.")
    
    # Input options
    parser.add_argument("problem_dir", type=str, nargs="?", default=None, 
                       help="Path to the problem directory (default: from settings)")
    parser.add_argument("--nbook", type=str, help="Path to specific notebook file to process")
    
    # Extraction options
    parser.add_argument("--extract-meta", action="store_true", 
                       help="Extract metadata from notebook and requirements.json")
    parser.add_argument("--extract-problem", action="store_true", 
                       help="Extract problem statement from notebook")
    parser.add_argument("--extract-solution", action="store_true", 
                       help="Extract solution from notebook")
    parser.add_argument("--extract-standard", action="store_true", 
                       help="Extract standard code from solution.md")
    
    # Language option
    parser.add_argument("-l", "--language", type=str, choices=["C++", "Python", "default"], default="default",
                       help="Programming language to use: C++, Python, or default (from settings) (default: default)")
    
    # Logging options
    parser.add_argument("--log-level", type=str, default="warning",
                       choices=['debug', 'info', 'warning', 'error', 'critical'],
                       help="Set the logging level (default: warning)")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress output except errors")
    
    args = parser.parse_args()
    
    # Setup logging with appropriate level
    log_level = logging.ERROR if args.quiet else get_log_level(args.log_level)
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    
    # Determine language to use
    if args.language == "default":
        try:
            settings = get_settings()
            language = settings.get("language", "C++")
        except Exception as e:
            logger.warning(f"Could not read settings, using C++ as default: {e}")
            language = "C++"
    else:
        language = args.language
    
    # Determine problem directory
    if args.nbook:
        # If specific notebook provided, use its parent directory
        notebook_path = Path(args.nbook)
        if not notebook_path.exists():
            print(f"❌ Notebook file not found: {notebook_path}")
            sys.exit(1)
        problem_dir = notebook_path.parent
        print(f"📓 Using notebook: {notebook_path}")
    else:
        # Use provided problem directory or default
        if args.problem_dir:
            problem_dir = Path(args.problem_dir)
        else:
            default_dir = get_default_problem_dir()
            if not default_dir:
                print("❌ No problem directory specified and no default found in settings")
                sys.exit(1)
            problem_dir = Path(default_dir)
        
        if not problem_dir.exists():
            print(f"❌ Problem directory not found: {problem_dir}")
            sys.exit(1)
        
        # Find notebook in problem directory
        notebook_path = find_notebook_in_problem_dir(problem_dir)
        if not notebook_path:
            print(f"❌ No Jupyter notebook found in {problem_dir}")
            sys.exit(1)
        print(f"📓 Found notebook: {notebook_path}")
    
    # Determine which extractions to perform
    if not any([args.extract_meta, args.extract_problem, args.extract_solution, args.extract_standard]):
        # If no specific extractions requested, perform all
        extract_meta = True
        extract_problem = True
        extract_solution = True
        extract_standard = True
        print("📋 No specific extractions requested, performing all extractions")
    else:
        extract_meta = args.extract_meta
        extract_problem = args.extract_problem
        extract_solution = args.extract_solution
        extract_standard = args.extract_standard
    
    # Track results
    results = {
        'metadata': False,
        'problem_statement': False,
        'solution': False,
        'standard': False
    }
    
    print(f"🔧 Processing: {problem_dir.name}")
    print(f"🌐 Language: {language}")
    print()
    
    # Extract metadata if requested
    if extract_meta:
        print("📊 Extracting metadata...", end=" ")
        notebook_metadata = parse_metadata_from_notebook(notebook_path, logger)
        
        if update_metadata_json(problem_dir, notebook_metadata, logger):
            results['metadata'] = True
            print("✅")
        else:
            print("❌")
    
    # Extract problem statement if requested
    if extract_problem:
        print("📄 Extracting problem statement...", end=" ")
        prompt_content = extract_prompt_from_notebook(notebook_path, logger)
        if save_prompt_to_problem_statement(problem_dir, prompt_content, logger):
            results['problem_statement'] = True
            print("✅")
        else:
            print("❌")
    
    # Extract solution if requested
    if extract_solution:
        print("💡 Extracting solution...", end=" ")
        solution_content = extract_solution_from_notebook(notebook_path, logger)
        if save_solution_to_file(problem_dir, solution_content, logger):
            results['solution'] = True
            print("✅")
        else:
            print("❌")
    
    # Extract standard code if requested
    if extract_standard:
        print("📝 Extracting standard code...", end=" ")
        solution_path = problem_dir / 'solution.md'
        if extract_standard_from_solution(solution_path, language, logger):
            results['standard'] = True
            print("✅")
        else:
            print("❌")
    
    # Check if all requested extractions succeeded
    requested_extractions = []
    if extract_meta:
        requested_extractions.append('metadata')
    if extract_problem:
        requested_extractions.append('problem_statement')
    if extract_solution:
        requested_extractions.append('solution')
    if extract_standard:
        requested_extractions.append('standard')
    
    # Check if all requested extractions succeeded
    all_requested_succeeded = all(results[extraction] for extraction in requested_extractions)
    
    if all_requested_succeeded:
        print("🎉 All requested extractions completed successfully!")
        sys.exit(0)
    else:
        failed_extractions = [k for k in requested_extractions if not results[k]]
        print(f"⚠️  Some extractions failed: {', '.join(failed_extractions)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
