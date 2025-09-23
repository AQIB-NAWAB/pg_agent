import sys
import re
import logging
import asyncio
import traceback
import argparse
import os
from pathlib import Path
from langchain_core.messages import HumanMessage
from pg_agent.utils.env import load_env, get_available_models, default_model
from pg_agent.utils.models import get_async_llm
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.parsing import extract_cpp_code

class ProgressTracker:
    def __init__(self, model_run_info):
        """
        Initialize progress tracker with model and run information.
        
        Args:
            model_run_info: List of tuples [(model_name, run_id), ...]
        """
        self._progress = {}
        self._model_run_info = model_run_info
        
        # Calculate the maximum model name length for alignment
        self._max_model_name_length = max(len(info[0]) for info in model_run_info) if model_run_info else 10
        
        # Initialize progress for each task
        for i, (model_name, run_id) in enumerate(model_run_info):
            self._progress[i] = {
                'model_name': model_name,
                'stage': "Not started",
                'run_id': run_id,
                'reasoning_len': 0,
                'response_len': 0
            }
        
        self._num_tasks = len(model_run_info)
        
        # Print initial status with proper spacing
        print(f"\nStarting generation for {len(set(info[0] for info in model_run_info))} model(s), {self._num_tasks} total runs...")
        self._print_progress_display()

    def _print_progress_display(self):
        """Print the complete progress display with proper formatting and alignment.
        
        Args:
            clear_lines: If True, clear each line before printing (for terminal updates)
        """
        print(f"Generation Progress:")
        for task_id in sorted(self._progress.keys()):
            p = self._progress[task_id]
            print(f"{p['model_name']:<{self._max_model_name_length}}: run {p['run_id']:2d} | {p['stage']:<12} | Reasoning: {p['reasoning_len']:6d} | Response: {p['response_len']:6d} chars")
    
    def _print_single_progress_line(self, task_id):
        """Print a single progress line for the specified task.
        
        Args:
            task_id: The task ID to print the progress line for
        """
        if task_id in self._progress:
            p = self._progress[task_id]
            print(f"\033[K{p['model_name']:<{self._max_model_name_length}}: run {p['run_id']:2d} | {p['stage']:<12} | Reasoning: {p['reasoning_len']:6d} | Response: {p['response_len']:6d} chars")

    def update_progress(self, context, progress):
        task_id = context["task_id"]
        run_id = context["run_id"]
        model_name = context["model_name"]
        stage = progress["stage"]
        reasoning_len = progress["lengths"]["reasoning"]
        response_len = progress["lengths"]["response"]

        self._progress[task_id] = {
            'model_name': model_name,
            'stage': stage,
            'run_id': run_id,
            'reasoning_len': reasoning_len,
            'response_len': response_len
        }
        
        # Save cursor position and move to the specific line for this task
        print("\0337", end="")  # Save cursor
        lines_to_move_up = self._num_tasks - task_id 
        print(f"\033[{lines_to_move_up}A", end="")  # Move up to the specific task line
        
        # Update only the current task's line
        self._print_single_progress_line(task_id)
        
        # Restore cursor position
        print("\0338", end="", flush=True)  # Restore cursor


async def generate_one(task_id, llm, prompt, index, problem_paths, model_name, logger, progress_tracker):
    messages = [HumanMessage(content=prompt)]
    
    # Try up to 3 attempts to get valid cpp code
    for attempt in range(3):
        try:
            # Get paths for code, prompt and raw response
            code_path, prompt_path, response_path, reasoning_path = problem_paths.get_run_paths(model_name, index)
            
            # Stream response directly to separate files
            response = await llm.ainvoke(
                messages,
                response_file=response_path,
                reasoning_file=reasoning_path,
                stream=True,
                context={"task_id": task_id, "run_id": index, "model_name": model_name},
                callback=progress_tracker.update_progress
            )
            
            # Try to extract cpp code from response
            cpp_code = extract_cpp_code(response.content)
            
            # If cpp_code is empty, try extracting from reasoning file
            if not cpp_code and reasoning_path.exists():
                logger.debug(f"Attempt {attempt + 1}: No C++ code found in response, trying reasoning file")
                try:
                    reasoning_content = reasoning_path.read_text(encoding="utf-8")
                    if reasoning_content.strip():
                        cpp_code = extract_cpp_code(reasoning_content)
                except Exception as read_error:
                    logger.debug(f"Could not read reasoning file: {read_error}")
            
            # If we still don't have cpp_code and this isn't the last attempt, retry
            if not cpp_code and attempt < 2:
                logger.warning(f"Attempt {attempt + 1}: No C++ code found, retrying... ({attempt + 2}/3)")
                continue
            
            # If we still don't have cpp_code after all attempts, log error but save what we have
            if not cpp_code:
                logger.error(f"❌ No C++ code found after 3 attempts for solution {index}")
                cpp_code = "// No C++ code could be extracted from the response"
            
            # Save the code to runs/
            code_path.write_text(cpp_code, encoding="utf-8")
            logger.info("✅ Saved code to: %s", code_path)
            
            # Save the reasoning to automation/runs/
            if hasattr(response, 'reasoning_content'):
                reasoning_path.write_text(response.reasoning_content, encoding="utf-8")
                logger.info("✅ Saved reasoning to: %s", reasoning_path)

            logger.info("✅ Streamed response to: %s", response_path)
            
            # If we got here with valid cpp_code, break out of retry loop
            if cpp_code and cpp_code != "// No C++ code could be extracted from the response":
                break
                
        except Exception as e:
            if attempt < 2:
                logger.warning(f"Attempt {attempt + 1} failed for solution {index}: {e}, retrying... ({attempt + 2}/3)")
                continue
            else:
                logger.error(f"❌ Error generating solution {index} after 3 attempts: {e}")
                raise e


async def generate_code_async(llm_configs, problem_text, num, problem_paths, logger):
    """
    Generate code for multiple models simultaneously.
    
    Args:
        llm_configs: List of tuples (llm_instance, model_name)
        problem_text: The problem statement
        num: Number of runs per model
        problem_paths: Problem directory paths
        logger: Logger instance
    """
    prompt = (
        "You are an expert competitive programmer. Please solve the following problem:\n\n"
        f"{problem_text}\n\n"
        "First analyze the problem, then provide your solution in C++. "
        "Consider edge cases, time complexity, and space complexity. "
        "Make sure your solution handles all constraints mentioned in the problem. "
        "Your final solution should be a complete, compilable C++ program."
    )
    
    # Prepare tasks for all models
    model_info = []
    
    for llm, model_name in llm_configs:
        # Find all existing solution indexes and the highest index for this model
        model_dir = problem_paths.runs / model_name
        existing_indexes = set()
        max_index = 0
        if model_dir.exists():
            for file in model_dir.glob("run_*.cpp"):
                match = re.search(r"run_(\d+)\.cpp", file.name)
                if match:
                    index = int(match.group(1))
                    existing_indexes.add(index)
                    max_index = max(max_index, index)
        
        # Find missing indexes up to max_index
        missing_indexes = sorted([i for i in range(1, max_index + 1) if i not in existing_indexes])
        
        # Get indexes to use for new solutions
        indexes_to_use = []
        # First use missing indexes
        while missing_indexes and len(indexes_to_use) < num:
            indexes_to_use.append(missing_indexes.pop(0))
        # Then add new indexes beyond max_index if needed
        while len(indexes_to_use) < num:
            max_index += 1
            indexes_to_use.append(max_index)
        
        # Save prompt for this model
        _, prompt_path, _, _ = problem_paths.get_run_paths(model_name, 0)
        prompt_path.write_text(prompt, encoding="utf-8")
        logger.info("✅ Saved prompt to: %s", prompt_path)
        logger.info("📋 Model %s will generate %d solutions: run numbers %s", 
                   model_name, len(indexes_to_use), ", ".join(map(str, indexes_to_use)))
        
        # Store model info for display
        model_info.append({
            'model_name': model_name,
            'llm': llm,
            'indexes': indexes_to_use
        })
    
    # Print output file paths pattern
    print(f"\nOutput files will be saved to:")
    problem_dir = problem_paths.runs.parent
    relative_problem_dir = os.path.relpath(problem_dir, Path.cwd())
    print(f"  Code     → {relative_problem_dir}/runs/<model_name>/run_<num>.cpp")
    print(f"  Response → {relative_problem_dir}/automation/runs/<model_name>/run_<num>.md")
    print(f"  Thinking → {relative_problem_dir}/automation/runs/<model_name>/run_<num>.reasoning.md")
    
    # Show which models and runs will be generated
    print(f"\nGenerating solutions:")
    for model_info_item in model_info:
        model_name = model_info_item['model_name']
        indexes = model_info_item['indexes']
        run_numbers = ", ".join(f"run_{i:02d}.cpp" for i in indexes)
        print(f"  {model_name}: {run_numbers}")
    
    # Prepare model_run_info for progress tracker and create tasks
    model_run_info = []
    tasks = []
    task_id = 0
    
    for model_info_item in model_info:
        model_name = model_info_item['model_name']
        llm = model_info_item['llm']
        indexes = model_info_item['indexes']
        for i in indexes:
            model_run_info.append((model_name, i))
            task_id += 1
    
    # Create progress tracker with model and run information
    progress_tracker = ProgressTracker(model_run_info)
    
    # Create tasks with progress tracker
    task_id = 0
    for model_info_item in model_info:
        model_name = model_info_item['model_name']
        llm = model_info_item['llm']
        indexes = model_info_item['indexes']
        for i in indexes:
            tasks.append(
                generate_one(task_id, llm, prompt, i, problem_paths, model_name, logger, progress_tracker)
            )
            task_id += 1
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks)


def parse_models(model_list):
    """Parse model names from argparse list, supporting comma-separated values within elements."""
    models = []
    
    for model_item in model_list:
        # Handle comma-separated values within individual arguments
        if ',' in model_item:
            models.extend([m.strip() for m in model_item.split(',') if m.strip()])
        else:
            models.append(model_item.strip())
    
    # Remove empty strings and duplicates while preserving order
    seen = set()
    result = []
    for model in models:
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    
    return result


def main():
    default_dir = get_default_problem_dir()
    available_models = get_available_models("model_sol")
    default_model_name = default_model("model_sol")
    
    parser = argparse.ArgumentParser(description="Generate C++ solutions using Qwen, Doubao, Tencent, etc.")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to problem directory (default: {default_dir})")
    parser.add_argument("--num", type=int, default=1,
                        help="Number of completions to generate per model")
    parser.add_argument("--provider", choices=["dashscope", "fireworks", "default"], default="default",
                        help="LLM provider for model (use 'default' to use model's default provider)")
    parser.add_argument("--model", nargs='+', default=[default_model_name],
                        help=f"Choose model(s) to use. Can be a single model or multiple models separated by spaces or commas. Available: {', '.join(available_models)}")
    parser.add_argument("--log-level", type=str, default="debug",
                        choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="Set the logging level (default: debug)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output except errors")
    
    args = parser.parse_args()
    log_level = logging.ERROR if args.quiet else get_log_level(args.log_level)
    
    problem_dir = Path(args.problem_dir)
    
    # Set up automatic log file using problem paths
    log_file = None
    if not args.quiet:  # Only log to file if not in quiet mode
        problem_paths = get_problem_paths(str(problem_dir))
        script_name = Path(__file__).stem  # Gets "07_model_sol" from "07_model_sol.py"
        log_file = problem_paths.automation / "logs" / f"{script_name}.log"
    
    setup_logging(log_level, str(log_file) if log_file else None, console_logging=False)
    logger = logging.getLogger(__name__)
    
    if log_file:
        logger.info("="*60)
        logger.info("🚀 Model Solution Generation Session Started")
        logger.info("="*60)
        logger.info("Command line arguments: %s", " ".join(sys.argv[1:]))
        logger.info("Log file: %s", log_file)

    try:
        # Parse model names
        model_names = parse_models(args.model)
        
        # Validate all model names
        for model_name in model_names:
            if model_name not in available_models:
                logger.error("❌ Invalid model: %s. Available models: %s", 
                           model_name, ", ".join(available_models))
                sys.exit(1)
        
        logger.info("🚀 Generating %d solution(s) per model for: %s", 
                   args.num, ", ".join(model_names))
        
        # Create LLM configurations for all models
        llm_configs = []
        for model_name in model_names:
            model_config = load_env(model=model_name, provider=args.provider)
            llm = get_async_llm(model_config)
            llm_configs.append((llm, model_name))
            logger.info("✅ Configured model: %s", model_name)
        
        # problem_paths already created above for logging, reuse it
        if 'problem_paths' not in locals():
            problem_paths = get_problem_paths(str(problem_dir))
        if not problem_paths.problem_statement.exists():
            logger.error("❌ Problem statement not found: %s", problem_paths.problem_statement)
            sys.exit(1)

        with open(problem_paths.problem_statement, "r", encoding="utf-8") as f:
            problem_text = f.read()
        
        asyncio.run(generate_code_async(llm_configs, problem_text, args.num, problem_paths, logger))
        
        # Add final status
        print("\nAll generations completed!")
        print("=" * 60)
        
        if log_file:
            logger.info("✅ All model generations completed successfully!")
            logger.info("="*60)

    except Exception as e:
        logger.error("❌ Execution error:")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        if log_file:
            logger.error("Session ended with error. Check log file for details: %s", log_file)
        sys.exit(1)


if __name__ == "__main__":
    main()
