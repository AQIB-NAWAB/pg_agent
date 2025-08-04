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
from pg_agent.utils.models import ChatBytedance, ChatAlibaba
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir
from pg_agent.utils.parsing import extract_cpp_code


async def generate_one(llm, prompt, index, output_dir, logger):
    messages = [HumanMessage(content=prompt)]
    try:
        response = await llm.ainvoke(messages)
        cpp_code = extract_cpp_code(response.content)
        file_path = output_dir / f"run_{index:02d}.cpp"
        file_path.write_text(cpp_code, encoding="utf-8")
        logger.info("✅ Saved: %s", file_path)
    except Exception as e:
        logger.error(f"❌ Error generating solution {index}: {e}")


async def generate_code_async(llm, problem_text, num, output_dir, logger):
    # Find the highest existing solution index
    existing_files = list(output_dir.glob("run_*.cpp"))
    max_index = 0
    for file in existing_files:
        # Try both formats: run_01.cpp and run_1.cpp
        match = re.search(r"run_(\d+)\.cpp", file.name)
        if match:
            index = int(match.group(1))
            max_index = max(max_index, index)

    prompt = (
        "Generate the complete and correct C++ code only for the following problem. "
        "Do not include any explanation, comments, thoughts or reasoning. Just the code:\n\n"
        f"{problem_text}"
    )
    tasks = [
        generate_one(llm, prompt, i, output_dir, logger)
        for i in range(max_index + 1, max_index + num + 1)
    ]
    await asyncio.gather(*tasks)


def main():
    env_keys = load_env()

    default_dir = get_default_problem_dir()
    parser = argparse.ArgumentParser(description="Generate C++ solutions using Qwen or Dubao")
    parser.add_argument("problem_dir", nargs="?", default=default_dir,
                        help=f"Path to problem directory (default: {default_dir})")
    parser.add_argument("--num", type=int, default=1,
                        help="Number of completions to generate")
    parser.add_argument("--model", choices=[
        "qwen3-coder-480b-a35b-instruct",
        "qwen3-235b-a22b-thinking-2507",
        "doubao-seed-1-6-thinking-250715"
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

    log_level = logging.ERROR if args.quiet else get_log_level(args.log_level)
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    problem_dir = Path(args.problem_dir)
    problem_statement_path = problem_dir / "problem_statement.md"

    try:
        if args.model not in env_keys:
            raise ValueError(f"Unsupported model: {args.model}")

        provider = env_keys[args.model]
        api_key = provider.get("api_key")
        model_name = provider.get("model")

        if not api_key:
            raise ValueError(f"API key not found for model: {args.model}")

        if not problem_statement_path.exists():
            logger.error("❌ Problem statement not found: %s", problem_statement_path)
            sys.exit(1)

        output_dir = problem_dir / "runs" / args.model
        output_dir.mkdir(parents=True, exist_ok=True)

        use_thinking = args.enable_thinking or "thinking" in args.model.lower()

        llm = ChatAlibaba(
            model=model_name,
            api_key=api_key,
            temperature=1.3,
            enable_thinking=use_thinking
        ) if args.model.startswith("qwen") else ChatBytedance(
            model=model_name,
            api_key=api_key,
            temperature=1.3
        )

        with open(problem_statement_path, "r", encoding="utf-8") as f:
            problem_text = f.read()

        logger.info("🚀 Generating %d solution(s) using model: %s%s",
                    args.num, args.model,
                    " (with thinking)" if use_thinking else "")
        asyncio.run(generate_code_async(llm, problem_text, args.num, output_dir, logger))

    except Exception as e:
        logger.error("❌ Execution error:")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
