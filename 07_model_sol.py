import os
import sys
import re
import logging
import asyncio
import traceback
import argparse
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from pg_agent.utils.env import load_env
from pg_agent.utils.models import get_async_llm
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.parsing import extract_cpp_code


async def generate_one(llm, prompt, index, problem_paths, model_name, logger):
    messages = [HumanMessage(content=prompt)]
    try:
        response = await llm.ainvoke(messages)
        cpp_code = extract_cpp_code(response.content)
        
        # Get paths for code, prompt and raw response
        code_path, prompt_path, response_path, reasoning_path = problem_paths.get_run_paths(model_name, index)
        
        # Save the code to runs/
        code_path.write_text(cpp_code, encoding="utf-8")
        logger.info("✅ Saved code to: %s", code_path)
        
        # Save the full response to automation/runs/
        response_path.write_text(response.content, encoding="utf-8")
        logger.info("✅ Saved full response to: %s", response_path)
        
        # Save the reasoning to automation/runs/
        if hasattr(response, 'reasoning_content'):
            reasoning_path.write_text(response.reasoning_content, encoding="utf-8")
            logger.info("✅ Saved reasoning to: %s", reasoning_path)
        
    except Exception as e:
        logger.error(f"❌ Error generating solution {index}: {e}")


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
    
    tasks = [
        generate_one(llm, prompt, i, problem_paths, model_name, logger)
        for i in indexes_to_use
    ]
    await asyncio.gather(*tasks)


def main():
    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate C++ solutions using Qwen, Doubao or Tencent models")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to problem directory (default: {default_dir})")
    parser.add_argument("--num", type=int, default=1,
                        help="Number of completions to generate")
    parser.add_argument("--provider", choices=["dashscope", "fireworks"], default="fireworks",
                    help="LLM provider to use for Qwen models (default: fireworks)")
    parser.add_argument("--model", choices=[
        "qwen3-coder-480b-a35b-instruct",
        "qwen3-235b-a22b-thinking-2507",
        "doubao-seed-1-6-thinking-250715",
        "hunyuan-t1-20250711",
        "hunyuan-turbos-20250604",
        "o3",
        "claude-opus-4-20250514",
    	"claude-opus-4-1-20250805",
    	"claude-sonnet-4-20250514"
    ], default="doubao-seed-1-6-thinking-250715",
        help="Choose model to use")
    parser.add_argument("--enable-thinking", action="store_true",
                        help="Enable internal thinking mode (Qwen only)")
    parser.add_argument("--log-level", type=str, default="info",
                        choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="Set the logging level (default: info)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output except errors")
    
    args = parser.parse_args()
    model_config = load_env(model=args.model, provider=args.provider)
    log_level = logging.ERROR if args.quiet else get_log_level(args.log_level)
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    problem_dir = Path(args.problem_dir)

    try:
        api_key = model_config.get("api_key")
        model_name = model_config.get("model")
        
        if not model_name:
            raise ValueError(f"Model name not found for model: {args.model}")

        if not api_key:
            raise ValueError(f"API key not found for model: {args.model}")

        problem_paths = get_problem_paths(str(problem_dir))
        if not problem_paths.problem_statement.exists():
            logger.error("❌ Problem statement not found: %s", problem_paths.problem_statement)
            sys.exit(1)

        use_thinking = args.enable_thinking or "thinking" in args.model.lower()
        max_tokens = model_config.get("max_tokens", None)

        # Get LLM instance
        llm = get_async_llm(
            model_type=args.model,
            model_name=model_name,
            api_key=api_key,
            max_tokens=max_tokens,
            enable_thinking=use_thinking
        )
        
        with open(problem_paths.problem_statement, "r", encoding="utf-8") as f:
            problem_text = f.read()

        logger.info("🚀 Generating %d solution(s) using model: %s%s",
                    args.num, args.model,
                    " (with thinking)" if use_thinking else "")
        asyncio.run(generate_code_async(llm, problem_text, args.num, problem_paths, args.model, logger))

    except Exception as e:
        logger.error("❌ Execution error:")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
