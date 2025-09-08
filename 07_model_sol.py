import sys
import re
import logging
import asyncio
import threading
import traceback
import argparse
from pathlib import Path
from langchain_core.messages import HumanMessage
from pg_agent.utils.env import load_env, get_available_models, default_model
from pg_agent.utils.models import get_async_llm
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.parsing import extract_cpp_code

class ProgressTracker:
    def __init__(self, num_tasks):
        self._progress = {}
        for i in range(num_tasks):
            self._progress[i] = {
                'model_name': "N/A",
                'stage': "Not started",
                'run_id': -1,
                'reasoning_len': 0,
                'response_len': 0
            }
        self._progress_lock = threading.Lock()
        self._progress_header_printed = False
        self._num_tasks = num_tasks

    def update_progress(self, context, progress):
        task_id = context["task_id"]
        run_id = context["run_id"]
        model_name = context["model_name"]
        stage = progress["stage"]
        reasoning_len = progress["lengths"]["reasoning"]
        response_len = progress["lengths"]["response"]

        with self._progress_lock:
            self._progress[task_id] = {
                'model_name': model_name,
                'stage': stage,
                'run_id': run_id,
                'reasoning_len': reasoning_len,
                'response_len': response_len
            }
            
            # Print header only once
            if not self._progress_header_printed:
                print("Generation Progress:")
                self._progress_header_printed = True
            
            # Save cursor position and move back to progress section
            print("\0337", end="")  # Save cursor
            print(f"\033[{self._num_tasks + 2}A", end="")  # Move up to progress section (+2 for header and blank line)
            
            # Print progress
            print("\033[K")  # Clear header line
            print("Generation Progress:")
            for task_id in sorted(self._progress.keys()):
                p = self._progress[task_id]
                print(f"\033[K{p['model_name']:<10}: run {p['run_id']:2d}: | {p['stage']:<10} | Reasoning: {p['reasoning_len']:5d} | Response: {p['response_len']:5d} chars")
            
            # Restore cursor position
            print("\0338", end="", flush=True)  # Restore cursor


async def generate_one(task_id, llm, prompt, index, problem_paths, model_name, logger, progress_tracker):
    messages = [HumanMessage(content=prompt)]
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
        cpp_code = extract_cpp_code(response.content)
        
        # Save the code to runs/
        code_path.write_text(cpp_code, encoding="utf-8")
        logger.debug("✅ Saved code to: %s", code_path)  # Changed to debug to avoid cluttering progress display
        
        # Save the reasoning to automation/runs/
        if hasattr(response, 'reasoning_content'):
            reasoning_path.write_text(response.reasoning_content, encoding="utf-8")
            logger.debug("✅ Saved reasoning to: %s", reasoning_path)  # Changed to debug

        logger.debug("✅ Streamed response to: %s", response_path)  # Changed to debug
        
    except Exception as e:
        logger.error(f"❌ Error generating solution {index}: {e}")
        raise e


async def generate_code_async(llm, problem_text, num, problem_paths, model_name, logger):
    # Find all existing solution indexes and the highest index
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

    prompt = (
        "You are an expert competitive programmer. Please solve the following problem:\n\n"
        f"{problem_text}\n\n"
        "First analyze the problem, then provide your solution in C++. "
        "Consider edge cases, time complexity, and space complexity. "
        "Make sure your solution handles all constraints mentioned in the problem. "
        "Your final solution should be a complete, compilable C++ program."
    )
    
    # Get paths for the first run to get prompt path
    _, prompt_path, _, _ = problem_paths.get_run_paths(model_name, 0)
    prompt_path.write_text(prompt, encoding="utf-8")
    logger.info("✅ Saved prompt to: %s", prompt_path)
    
    # Print output file paths for each run
    print("\nOutput files:")
    for i in indexes_to_use:
        code_path, _, response_path, reasoning_path = problem_paths.get_run_paths(model_name, i)
        print(f"\nRun {i}:")
        print(f"  Code     → {code_path}")
        print(f"  Response → {response_path}")
        print(f"  Thinking → {reasoning_path}")
    
    # Get actual model parameters using the model's method
    dummy_messages = [HumanMessage(content="test")]
    params = await llm.get_completion_params(dummy_messages, stream=True)
    
    print("\nModel parameters:")
    for k, v in params.items():
        if k != "messages":  # Skip messages as it's not a parameter
            print(f"  {k}: {v}")
    
    # Add extra newlines based on number of runs to prevent progress display from overwriting paths
    num_tasks = len(indexes_to_use)
    print(f"\nStarting generation...{chr(10) * num_tasks}\n")  # One line per run plus extra for header
    
    progress_tracker = ProgressTracker(num_tasks)
    tasks = [
        generate_one(task_id, llm, prompt, i, problem_paths, model_name, logger, progress_tracker)
        for task_id, i in enumerate(indexes_to_use)
    ]
    await asyncio.gather(*tasks)


def main():
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate C++ solutions using Qwen, Doubao, Tencent, etc.")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to problem directory (default: {default_dir})")
    parser.add_argument("--num", type=int, default=1,
                        help="Number of completions to generate")
    parser.add_argument("--provider", choices=["dashscope", "fireworks", "default"], default="default",
                        help="LLM provider for model (use 'default' to use model's default provider)")
    parser.add_argument("--model", choices=get_available_models("model_sol"), default=default_model("model_sol"),
                        help="Choose model to use")
    parser.add_argument("--enable-thinking", action="store_true",
                        help="Enable internal thinking mode (Qwen only)")
    parser.add_argument("--log-level", type=str, default="info",
                        choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="Set the logging level (default: info)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output except errors")
    
    args = parser.parse_args()
    log_level = logging.ERROR if args.quiet else get_log_level(args.log_level)
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    problem_dir = Path(args.problem_dir)

    try:
        model_config = load_env(model=args.model, provider=args.provider)
        use_thinking = args.enable_thinking or "thinking" in args.model.lower()
        model_config["parameters"]["enable_thinking"] = use_thinking

        # Get LLM instance
        llm = get_async_llm(model_config)
    
        problem_paths = get_problem_paths(str(problem_dir))
        if not problem_paths.problem_statement.exists():
            logger.error("❌ Problem statement not found: %s", problem_paths.problem_statement)
            sys.exit(1)

        with open(problem_paths.problem_statement, "r", encoding="utf-8") as f:
            problem_text = f.read()

        logger.info("🚀 Generating %d solution(s) using model: %s%s",
                    args.num, args.model,
                    " (with thinking)" if use_thinking else "")
        
        print("\nGeneration Progress:")
        
        asyncio.run(generate_code_async(llm, problem_text, args.num, problem_paths, args.model, logger))
        
        # Add final status
        print("\nAll generations completed!")
        print("=" * 60)

    except Exception as e:
        logger.error("❌ Execution error:")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()