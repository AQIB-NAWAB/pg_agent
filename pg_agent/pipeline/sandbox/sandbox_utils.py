import docker
import os
import re
from pathlib import Path
import tempfile
import shutil
import subprocess
from typing import List, Dict, Tuple

# Use a versioned tag to avoid rebuilding unnecessarily
DOCKER_IMAGE_TAG = "pg-agent/multi-language-sandbox:2.0"

def _build_image_if_not_exists(client: docker.DockerClient, image_tag: str):
    """Checks if the image exists locally and builds it if it doesn't."""
    try:
        client.images.get(image_tag)
    except docker.errors.ImageNotFound:
        print(f"Docker image '{image_tag}' not found. Building...")
        sandbox_dir = Path(__file__).parent
        try:
            client.images.build(path=str(sandbox_dir), tag=image_tag, rm=True)
            print(f"Build successful. Image tag: {image_tag}")
        except docker.errors.BuildError as e:
            print(f"FATAL: Docker build failed: {e}")
            raise

def _run_command_in_container(image_tag: str, command: str, work_dir: Path, input_data: bytes = None) -> (int, str, str):
    """A robust function to run a command in a container using the Docker CLI via subprocess."""
    client = docker.from_env()
    _build_image_if_not_exists(client, image_tag)
    abs_work_dir = str(work_dir.resolve())
    docker_command = [
        "docker", "run", "--rm", "-i", "-w", "/usr/src/app",
        "-v", f"{abs_work_dir}:/usr/src/app",
        "--memory=512m", "--cpu-shares=1024",
        image_tag, "/bin/bash", "-c", command
    ]
    process = subprocess.run(
        docker_command, input=input_data,
        capture_output=True, timeout=120
    )
    stdout = process.stdout.decode('utf-8', errors='ignore')
    stderr = process.stderr.decode('utf-8', errors='ignore')
    return process.returncode, stdout, stderr

def run_generator_script(script_path: str, output_dir: Path, language: str = "C++"):
    """Compiles and runs a generator script inside the mounted output_dir using runner.sh."""
    work_dir = output_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy script with appropriate name based on language
    script_name = "generator.cpp" if language == "C++" else "generator.py"
    shutil.copy(script_path, work_dir / script_name)
    
    # Copy and prepare runner.sh
    runner_sh_path = Path(__file__).parent / "runner.sh"
    if runner_sh_path.exists():
        runner_content = runner_sh_path.read_text(encoding="utf-8").replace('\r\n', '\n')
        (work_dir / "runner.sh").write_text(runner_content, encoding="utf-8", newline='\n')
        (work_dir / "runner.sh").chmod(0o755)
    else:
        raise FileNotFoundError(f"runner.sh not found at expected location: {runner_sh_path}")
    
    # Use runner.sh to generate test cases, passing language as parameter
    command = f"/bin/bash runner.sh generate {language}"
    status_code, stdout, stderr = _run_command_in_container(DOCKER_IMAGE_TAG, command, work_dir)
    print(f"Generator script output:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
    if status_code != 0:
        raise Exception(f"Generator script failed:\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

def run_validation_suite(validator_path: str, all_input_files: List[Path], language: str = "C++") -> Dict:
    """
    Uses the central Docker utility to run a validator against all test cases
    and returns a detailed report object.
    """
    debug = True

    if not all_input_files:
        if(debug): print("No input files to validate.")
        return {"summary": {"status": "SUCCESS", "message": "No input files to validate."}, "results": []}
    
    with tempfile.TemporaryDirectory() as temp_dir_str:
        work_dir = Path(temp_dir_str)
        # Prepare the temporary directory with the validator and all input files
        validator_filename = "validator.cpp" if language == "C++" else "validator.py"
        shutil.copy(validator_path, work_dir / validator_filename)
        for in_file in all_input_files:
            shutil.copy(in_file, work_dir / in_file.name)
        
        # Do not use shutil.copy for shell scripts due to line ending issues.
        # Instead, read the content, normalize line endings to LF (\n),
        # and write it back out to ensure Linux compatibility.
        runner_sh_path = Path(__file__).parent / "runner.sh"
        if runner_sh_path.exists():
            runner_content = runner_sh_path.read_text(encoding="utf-8").replace('\r\n', '\n')
            (work_dir / "runner.sh").write_text(runner_content, encoding="utf-8", newline='\n')
            (work_dir / "runner.sh").chmod(0o755)
        else:
            raise FileNotFoundError(f"runner.sh not found at expected location: {runner_sh_path}")

        # Define the command to be executed inside the container
        command = f"/bin/bash runner.sh validate_suite {language}"
        
        try:
            if debug:
                print(f"Running validation suite in {work_dir}")

            status_code, stdout, stderr = _run_command_in_container(
                DOCKER_IMAGE_TAG, command, work_dir
            )
            if status_code != 0:
                raise Exception(stderr)
                
            results_output = stdout

        except Exception as e:
            if debug:
                print(f"Error running validation suite: {e}")
            return {"summary": {"status": "ERROR", "message": "Docker execution for validation failed."}, "details": str(e), "results": []}

        # (The rest of the function remains the same...)
        detailed_results = []
        valid_count, invalid_count = 0, 0
        
        result_blocks = results_output.strip().split("--- RESULT ---")[1:]
        if debug:
            print(f"Found {len(result_blocks)} result blocks in output")

        for block in result_blocks:
            try:
                test_name = re.search(r"TEST_NAME:(.*)", block).group(1).strip()
                status = re.search(r"STATUS:(.*)", block).group(1).strip()
                result_item = {"test_name": test_name, "status": status}

                if status == "INVALID":
                    reason = re.search(r"REASON_START\n(.*)\nREASON_END", block, re.DOTALL).group(1).strip()
                    result_item["reason"] = reason
                    invalid_count += 1
                else:
                    valid_count += 1
                
                detailed_results.append(result_item)
            except Exception:
                invalid_count += 1
                detailed_results.append({"test_name": "unknown", "status": "PARSING_ERROR"})

    if debug:
        print(f"Validation complete: {valid_count} valid, {invalid_count} invalid out of {len(all_input_files)} total")
        
    final_status = "SUCCESS" if invalid_count == 0 else "FAILURE"
    summary = {"status": final_status, "valid": valid_count, "invalid": invalid_count, "total": len(all_input_files)}

    return {"summary": summary, "results": detailed_results}

def run_test_suite(solution_path: str, test_cases_dir: Path, time_limit: float, memory_limit: int, run_full_suite: bool, language: str = "C++"):
    """
    Runs a single solution against a directory of test cases efficiently.
    Compiles once, then runs all tests in a single container.
    """
    work_dir = test_cases_dir
    
    # Define source and destination paths using pathlib
    src_path = Path(solution_path)
    file_ext = "cpp" if language == "C++" else "py"
    dest_path = work_dir / f"solution.{file_ext}"

    # Only copy if the source and destination are not the same file.
    # We use .resolve() to get the absolute, canonical path, which correctly
    # handles different path syntaxes ('/' vs '\') on Windows.
    if src_path.resolve() != dest_path.resolve():
        shutil.copy(str(src_path), dest_path)
    
    runner_sh_content = (Path(__file__).parent / "runner.sh").read_text().replace('\r\n', '\n')
    (work_dir / "runner.sh").write_text(runner_sh_content, newline='\n')
    os.chmod(work_dir / "runner.sh", 0o755)

    solution_file = f"solution.{file_ext}"
    executable_name = "solution_executable" if language == "C++" else "solution.py"
    command = f"./runner.sh execute_suite {time_limit} {memory_limit} {run_full_suite} {solution_file} {executable_name} {language}"
    status_code, stdout, stderr = _run_command_in_container(DOCKER_IMAGE_TAG, command, work_dir=work_dir)
    
    if status_code != 0:
        raise Exception(f"Test suite execution failed:\nSTATUS_CODE:\n{status_code}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

    return stdout, stderr


def run_solution_on_test_case(solution_path: str, input_file: Path, time_limit: float) -> (bool, str):
    """Runs a solution against an input file with a timeout. Returns (timed_out, output)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        shutil.copy(solution_path, work_dir / "solution.cpp")
        command = f"g++ -std=c++14 -O2 -o solution solution.cpp && timeout {time_limit} ./solution"
        input_data = input_file.read_bytes()
        status_code, stdout, stderr = _run_command_in_container(DOCKER_IMAGE_TAG, command, work_dir, input_data=input_data)
        timed_out = status_code == 124
        if status_code not in [0, 124]:
            print(f"Solution run failed with stderr:\n{stderr}")
        return timed_out, stdout

def run_single_test(solution_code: str, input_data: str) -> Tuple[bool, str, str]:
    """Runs a single piece of code (as a string) against a single input string.
    
    Returns:
        Tuple containing:
        - success: True if compilation and execution succeeded
        - output: stdout from the program (or compilation error)
        - error: stderr from compilation/execution
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        (work_dir / "solution.cpp").write_text(solution_code)
        command = "g++ -std=c++14 -O2 -o solution solution.cpp && ./solution"
        status_code, stdout, stderr = _run_command_in_container(DOCKER_IMAGE_TAG, command, work_dir, input_data=input_data.encode('utf-8'))
        if status_code != 0:
            print(f"run_single_test failed with stderr:\n{stderr}")
        return status_code == 0, stdout, stderr
