import os
import sys
import json
import argparse
import logging
import difflib
import subprocess
import statistics
import datetime
from pathlib import Path
from collections import defaultdict

# Dependency Imports
from pg_agent.utils.logging import setup_logging, get_log_level
from pg_agent.utils.structure import get_default_problem_dir, get_problem_paths
from pg_agent.utils.test_runner import run_tests, find_test_cases
from pg_agent.utils.env import get_available_models
# --- Constants ---
SPECIAL_SOLUTIONS = ["solution_bf.cpp", "standard.cpp"]
ALL_MODELS = get_available_models("model_sol")

ERROR_CODES = {
    "WA": "Wrong Answer", "TLE": "Time Limit Exceeded", "NZEC": "Non-Zero Exit Code",
    "SIGSEGV": "Segmentation Fault", "SIGABRT": "Abort Signal", "SIGFPE": "Floating-Point Exception",
    "RTE": "Other Runtime Error", "CE": "Compilation Error"
}

# --- Generation Logic ---
def generate_solutions_via_subprocess(problem_dir: Path, models_to_run: list[str], num_runs: int, logger: logging.Logger):
    """Calls 07_models_sol.py as a subprocess to generate solutions."""
    generator_script_path = Path(__file__).parent / "07_model_sol.py"
    if not generator_script_path.exists():
        logger.error(f"Generator script not found at: {generator_script_path}")
        return

    for model_id in models_to_run:
        logger.info(f"🚀 Launching generator for model: {model_id} ({num_runs} runs)...")
        command = [
            sys.executable, str(generator_script_path), str(problem_dir),
            "--model", model_id, "--num", str(num_runs),
        ]
        try:
            subprocess.run(command, check=True, text=True, cwd=Path(__file__).parent)
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Subprocess for model {model_id} failed with exit code {e.returncode}.")
        except FileNotFoundError:
            logger.error(f"❌ Could not execute script. Is '{sys.executable}' a valid python interpreter?")

# --- Reporting Logic ---

def _create_smart_diff(expected: str, actual: str, line_threshold: int) -> str:
    """Creates a full diff for small outputs or a contextual snippet for large ones."""
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()

    if len(expected_lines) < line_threshold and len(actual_lines) < line_threshold:
        return f"**Expected Output:**\n```\n{expected}\n```\n**Actual Output:**\n```\n{actual}\n```"
    else:
        diff = difflib.unified_diff(
            expected_lines, actual_lines,
            fromfile='expected.out', tofile='actual.out', lineterm='',
        )
        diff_snippet = '\n'.join(list(diff)[:50])
        if not diff_snippet:
             return "Outputs were different, but no diff snippet could be generated (e.g., trailing whitespace)."
        return f"**Difference Snippet (first 50 lines of diff):**\n```diff\n{diff_snippet}\n```"


def generate_reports(report_data: dict, report_dir: Path, settings: dict):
    """Orchestrates the creation of all Markdown reports in a hierarchical structure."""
    
    def get_error_legend() -> str:
        legend = "**Error Code Legend:**\n\n"
        for code, desc in ERROR_CODES.items():
            legend += f"- **{code}**: {desc}\n"
        return legend + "\n"

    def generate_individual_report(sol_name: str, data: dict, test_cases_map: dict):
        model_name = sol_name.split('/')[0] if '/' in sol_name else "special_solutions"
        run_name_stem = Path(sol_name.replace('/', '_')).stem
        
        model_report_dir = report_dir / model_name
        model_report_dir.mkdir(exist_ok=True)
        file_path = model_report_dir / f"{run_name_stem}.md"

        smart_diff_threshold = settings.get("smart_diff_line_threshold", 50)
        summary = data.get('summary', {})
        results = data.get('results', [])

        with file_path.open("w", encoding="utf-8") as f:
            f.write(f"# Detailed Report for `{sol_name}`\n\n")
            
            status = summary.get('status', 'ERROR')
            if status == 'COMPILATION_ERROR':
                f.write(f"**Overall Status:** ❌ COMPILATION ERROR\n")
            elif status == 'SUCCESS':
                f.write(f"**Overall Status:** ✅ SUCCESS\n")
            else:
                f.write(f"**Overall Status:** ❌ FAILURE\n")
                
            f.write(f"**Score:** {summary.get('passed', 0)} / {summary.get('total_available', 0)} ({summary.get('total_run', 0)} tests executed)\n\n")
            f.write(f"**Compilation Command:** `g++ -std=c++20 -O2 -w -o executable solution.cpp`\n\n")

            f.write("## Test Case Results\n\n")
            f.write("| Test Case | Status | Time (s) | Memory (MB) |\n")
            f.write("|---|---|---|---|\n")
            for res in results:
                time_s = f"{(res.get('execution_time_ms', 0) / 1000):.4f}"
                mem_mb = f"{(res.get('memory_usage_kb', 0) / 1024):.2f}"
                f.write(f"| `{res.get('test_name', 'N/A')}` | `{res.get('status', 'N/A')}` | {time_s} | {mem_mb} |\n")

            failures = [res for res in results if res.get("status") != "PASSED"]
            if failures:
                f.write("\n## Failure Details\n\n")
                for failure in failures:
                    f.write(f"### Test: `{failure.get('test_name', 'N/A')}`\n\n")
                    f.write(f"**Status:** `{failure.get('status', 'N/A')}`\n\n")
                    if failure.get('status') == 'COMPILATION_ERROR':
                        f.write(f"**Compiler Output:**\n```\n{failure.get('details', 'N/A')}\n```\n")
                    elif failure.get('status') == 'WRONG_ANSWER':
                        original_tc = test_cases_map.get(failure.get('test_name'))
                        if original_tc:
                            diff_report = _create_smart_diff(original_tc.get('output', ''), failure.get('actual_output', ''), smart_diff_threshold)
                            f.write(diff_report + "\n")

    # --- Main Report Generation ---
    overall_path = report_dir / "overall.md"
    results_by_model = defaultdict(list)
    for sol_name, data in report_data["solutions"].items():
        model_name = sol_name.split('/')[0] if '/' in sol_name else sol_name
        results_by_model[model_name].append((sol_name, data))
    
    with overall_path.open("w", encoding="utf-8") as f:
        f.write(f"# Overall Test Report for {report_data['problem_name']}\n\n")
        f.write(get_error_legend())

        f.write("## Detailed Model Performance\n\n")
        for model_name, runs in sorted(results_by_model.items()):
            f.write(f"### Model: `{model_name}`\n\n")
            f.write("| Run File | Status | Score | Avg Time (s) | Max Time (s) | Avg Mem (MB) | Max Mem (MB) | Errors (WA/TLE/RTE/CE) |\n")
            f.write("|---|---|---|---|---|---|---|---|\n")
            for run_name, run_data in runs:
                summary = run_data.get('summary', {})
                results = run_data.get('results', [])
                
                score = f"{summary.get('passed', 0)}/{summary.get('total_run', 0)}/{summary.get('total_available', 0)}"
                
                status = summary.get("status")
                if status == 'COMPILATION_ERROR':
                    status_icon = "❌ CE"
                    error_str = f"0/0/0/{summary.get('total_available', 1)}"
                elif status == 'SUCCESS':
                    status_icon = "✅ PASS"
                    error_str = "0/0/0/0"
                elif status in ('FAILURE', 'PARTIAL_SUCCESS'):
                    status_icon = "❌ FAIL"
                    wa = sum(1 for r in results if r['status'] == 'WRONG_ANSWER')
                    tle = sum(1 for r in results if r['status'] == 'TIME_LIMIT_EXCEEDED')
                    rte = summary.get('failed', 0) - wa - tle
                    error_str = f"{wa}/{tle}/{rte}/0"
                else:
                    status_icon = "❓ ERROR"
                    error_str = "0/0/1/0"

                times_ms = [r['execution_time_ms'] for r in results if r.get('status') == 'PASSED']
                mems_kb = [r['memory_usage_kb'] for r in results if r.get('status') == 'PASSED']
                avg_time_s = (statistics.mean(times_ms) / 1000) if times_ms else 0
                max_time_s = (max(times_ms) / 1000) if times_ms else 0
                avg_mem_mb = (statistics.mean(mems_kb) / 1024) if mems_kb else 0
                max_mem_mb = (max(mems_kb) / 1024) if mems_kb else 0

                f.write(f"| `{run_name}` | {status_icon} | {score} | {avg_time_s:.4f} | {max_time_s:.4f} | {avg_mem_mb:.2f} | {max_mem_mb:.2f} | {error_str} |\n")
            f.write("\n")
            
        f.write("---\n\n## Overall Model Comparison\n\n")
        f.write("| Model | Total Runs | Successful Runs | Failed Runs | Pass Rate |\n")
        f.write("|---|---|---|---|---|\n")
        for model_name, runs in sorted(results_by_model.items()):
            total_runs = len(runs)
            successful_runs = sum(1 for _, data in runs if data['summary'].get('status') == 'SUCCESS')
            failed_runs = total_runs - successful_runs
            pass_rate = f"{(successful_runs / total_runs * 100):.1f}%" if total_runs > 0 else "N/A"
            f.write(f"| `{model_name}` | {total_runs} | {successful_runs} | {failed_runs} | {pass_rate} |\n")

    test_cases_map = {tc['name']: tc for tc in report_data.get('test_cases_data', [])}
    for sol_name, data in report_data["solutions"].items():
        generate_individual_report(sol_name, data, test_cases_map)


def print_terminal_summary(report_data: dict):
    """Prints a final, concise summary table to the terminal without external dependencies."""
    headers = ["Solution File", "Status", "Score"]
    rows = []
    for sol_name, data in sorted(report_data["solutions"].items()):
        summary = data.get('summary', {})
        status = summary.get('status', 'ERROR')
        if status == 'COMPILATION_ERROR':
            status = 'COMPILE_ERR'
        
        score = f"{summary.get('passed', 0)}/{summary.get('total_available', 0)} ({summary.get('total_run', 0)} executed)"
        rows.append([sol_name, status, score])

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Create format strings
    header_format = " | ".join([f"{{:<{w}}}" for w in widths])
    row_format = " | ".join([f"{{:<{w}}}" for w in widths])
    separator = "+-" + "-+-".join(['-' * w for w in widths]) + "-+"

    # Print table
    print("\n--- Final Test Summary ---")
    print(f"Problem: {report_data['problem_name']}")
    print(separator)
    print(f"| {header_format.format(*headers)} |")
    print(separator)
    for row in rows:
        print(f"| {row_format.format(*row)} |")
    print(separator)


def main():
    parser = argparse.ArgumentParser(description="Generate and/or test external model solutions.")
    parser.add_argument("problem_dir", type=str, nargs="?", default=get_default_problem_dir(), help="Path to the problem directory.")
    # Generation flags
    parser.add_argument("--generate", action="store_true", help="Enable the solution generation phase.")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated list of models for generation.")
    parser.add_argument("--all", action="store_true", help="Generate solutions for all hardcoded models.")
    parser.add_argument("--num", type=int, default=1, help="Number of solutions to generate per model.")
    # Testing flags
    parser.add_argument("--full", action="store_true", help="Run all tests for each solution; don't stop on first failure.")
    parser.add_argument("--solution", type=str, help="Path to a single specific solution file to test.")
    parser.add_argument("--solutions-dir", type=str, help="Path to a directory of solutions to test.")
    parser.add_argument("--time-limit", type=float, default=5.0, help="Time limit in seconds for each test case.")
    parser.add_argument("--memory", type=int, default=512, help="Memory limit for Docker (e.g., '256m').")
    parser.add_argument("--cpus", type=str, default="1.5", help="CPU limit for Docker (e.g., '1.5').")
    
    args = parser.parse_args()

    # Setup
    setup_logging()
    logger = logging.getLogger(__name__)

    if not args.generate:
        logger.info("No generation requested. Proceeding with testing only.")

    problem_dir = Path(args.problem_dir)
    paths = get_problem_paths(problem_dir)
    problem_metadata = {}

    # check if problem directory exists and search for metadata files
    if problem_dir.is_dir():
        # Search for metadata files in order of preference
        metadata_files = ["requirements.json", "metadata.json"]
        problem_config_metadata_path = None
        
        for metadata_file in metadata_files:
            candidate_path = problem_dir / metadata_file
            if candidate_path.exists():
                problem_config_metadata_path = candidate_path
                break
        
        if problem_config_metadata_path:
            try:
                problem_metadata = json.loads(problem_config_metadata_path.read_text(encoding="utf-8"))
                logger.info(f"Loaded problem metadata from {problem_config_metadata_path}")
            except json.JSONDecodeError:
                logger.warning(f"Warning: Invalid JSON in {problem_config_metadata_path}. Proceeding without metadata.")
        else:
            logger.warning(f"Warning: No metadata file found in {problem_dir}. Looked for: {', '.join(metadata_files)}. Proceeding without metadata.")
            
    # --- Generation Phase ---
    if args.generate:
        if not args.models and not args.all:
            parser.error("--generate requires --models or --all to be specified.")
        logger.info("--- Starting Generation Phase (via Subprocess) ---")
        models_to_run = ALL_MODELS if args.all else [m.strip() for m in args.models.split(',')]
        generate_solutions_via_subprocess(problem_dir, models_to_run, args.num, logger)
        logger.info("--- Generation Phase Complete ---")

    # --- Testing Phase ---
    logger.info("--- Starting Testing Phase ---")
    all_test_cases = find_test_cases(paths.test_cases)
    if not all_test_cases:
        logger.error(f"Error: No valid test cases found in '{paths.test_cases}'")
        sys.exit(1)

    try:
        settings = json.loads((Path.cwd() / "pg_agent_settings.json").read_text())
    except FileNotFoundError:
        settings = {}

    report_data = {"problem_name": problem_dir.name, "solutions": {}, "test_cases_data": all_test_cases}
    
    # Discover solutions to test
    solutions_to_test = {} # Use dict to avoid duplicates: {absolute_path: unique_name_for_report}
    if args.solution:
        sol_path = Path(args.solution).resolve()
        if sol_path.exists(): solutions_to_test[sol_path] = sol_path.name
    elif args.solutions_dir:
        sol_dir = Path(args.solutions_dir).resolve()
        if sol_dir.is_dir():
            for cpp_file in sorted(sol_dir.glob("*.cpp")):
                solutions_to_test[cpp_file] = f"{sol_dir.name}/{cpp_file.name}"
    else:
        if paths.runs.exists():
            for folder in sorted(paths.runs.iterdir()):
                if folder.is_dir():
                    for cpp_file in sorted(folder.glob("*.cpp")):
                        solutions_to_test[cpp_file.resolve()] = f"{folder.name}/{cpp_file.name}"
        for sol_name in SPECIAL_SOLUTIONS:
            sol_path = problem_dir.resolve() / sol_name
            if sol_path.exists():
                solutions_to_test[sol_path] = sol_name
    
    if not solutions_to_test:
        logger.error("Error: No solutions found to test.")
        sys.exit(1)

    # Main Execution Loop
    total_solutions = len(solutions_to_test)
    logger.info(f"Found {total_solutions} solution(s) to test.")
    
    for i, (sol_path, unique_name) in enumerate(solutions_to_test.items()):
        logger.info(f"--- ({i+1}/{total_solutions}) Testing solution: {unique_name} ---")
        solution_code = sol_path.read_text(encoding="utf-8")

        _time_limit = problem_metadata.get("time", args.time_limit)
        _memory = problem_metadata.get("space", args.memory)
        

        test_report = run_tests(
            solution_code,
            all_test_cases,
            time_limit=_time_limit,
            run_full_suite=args.full,
            memory_limit=_memory,
            cpu_limit=args.cpus
        )
        report_data["solutions"][unique_name] = test_report
    
    # Final Reporting
    print_terminal_summary(report_data)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = paths.reports_dir / f"{problem_dir.name}_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    generate_reports(report_data, report_dir, settings)
    
    (report_dir / "summary.json").write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info(f"All reports generated in: {report_dir}")
    logger.info("--- Testing Phase Complete ---")

if __name__ == "__main__":
    main()