import json
from pathlib import Path
from typing import Dict, Optional

class ProblemPaths:
    """Represents the standard paths within a problem directory."""
    def __init__(self, problem_dir: Path):
        self.root = problem_dir
        # Core problem files
        self.problem_statement = self.root / "problem_statement.md"
        self.standard_solution = self.root / "standard.cpp"
        self.bruteforce_solution = self.root / "solution_bf.cpp"  # Main bruteforce solution path
        self.root_validator = self.root / "validator.cpp"  # Validator in root directory
        
        # Generator files in root
        self.test_generator = self.root / "test_generator.cpp"  # Basic test generator
        self.edge_generator = self.root / "edge_generator.cpp"  # Edge case generator
        
        # Automation directory structure
        self.automation = self.root / "automation"
        self.automation_bruteforce_dir = self.automation / "bruteForceSol"
        self.automation_settings = self.automation / "automation_settings.json"
        self.optimal_dir = self.automation / "optimalSol"
        self.qwen = self.root / "qwen"
        self.test_cases = self.root / "test_cases"
        self.automation_validator = self.automation / "validator.cpp"  # Validator in automation directory
        self.runs = self.root / "runs"  # Directory for model runs (clean code)
        self.automation_runs = self.automation / "runs"  # Directory for raw model outputs

    def get_run_paths(self, model_name: str, index: int) -> tuple[Path, Path, Path]:
        """Gets the paths for code and response files for a specific run.
        
        Args:
            model_name: Name of the model used
            index: Run index
            
        Returns:
            Tuple of (code_path, prompt_path, response_path) where:
            - code_path: Path to the clean C++ code file in runs/
            - prompt_path: Path to save the prompt in runs/
            - response_path: Path to save the raw response in automation/runs/
        """
        # Create directories
        model_dir = self.runs / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        automation_model_dir = self.automation_runs / model_name
        automation_model_dir.mkdir(parents=True, exist_ok=True)
        
        return (
            model_dir / f"run_{index:02d}.cpp",  # Clean code
            model_dir / "prompt.txt",  # Prompt
            automation_model_dir / f"run_{index:02d}.md"  # Raw response
        )

    @property
    def validator(self) -> Path:
        """Gets the validator path, preferring root directory over automation directory."""
        return self.root_validator if self.root_validator.exists() else self.automation_validator

    def get_optimal_path(self, version: int) -> Path:
        """Gets the path for a specific version of optimal solution."""
        return self.optimal_dir / f"optimalSolution_v{version}.cpp"

    def get_settings(self) -> Dict:
        """Reads and returns the automation settings."""
        if not self.automation_settings.exists():
            return {}
        try:
            return json.loads(self.automation_settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON in settings file: {self.automation_settings}")
            return {}

    def update_settings(self, settings: Dict) -> None:
        """Updates the automation settings file."""
        self.automation.mkdir(exist_ok=True)
        self.automation_settings.write_text(
            json.dumps(settings, indent=2, sort_keys=True),
            encoding="utf-8"
        )

def get_default_problem_dir() -> Optional[str]:
    """Get the default problem directory from settings."""
    settings_path = Path(__file__).parent.parent.parent / "pg_agent_settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        # Get the relative path from settings
        default_dir = settings.get("problem_directory", "")
        # Resolve it relative to current directory
        resolved_path = Path.cwd() / default_dir
        # Resolve any .. or . in the path
        default_dir = str(resolved_path.resolve())
        return default_dir
    except Exception as e:
        print(f"Warning: Could not read default problem directory from settings: {e}")
        return None

def get_problem_paths(problem_dir: str) -> ProblemPaths:
    """Creates a ProblemPaths object for the given problem directory."""
    return ProblemPaths(Path(problem_dir)) 