import json
from pathlib import Path
from typing import Dict, Optional

class ProblemPaths:
    """Represents the standard paths within a problem directory."""
    def __init__(self, problem_dir: Path):
        self.root = problem_dir
        self.problem_statement = self.root / "problem_statement.md"
        self.standard_solution = self.root / "standard.cpp"
        self.bruteforce_solution = self.root / "solution_bf.cpp"  # Add bruteforce solution path
        self.automation = self.root / "automation"
        self.automation_settings = self.automation / "automation_settings.json"
        self.bruteforce_dir = self.automation / "bruteForceSol"
        self.optimal_dir = self.automation / "optimalSol"
        self.test_cases = self.root / "test_cases"

    def get_bruteforce_path(self, version: int) -> Path:
        """Gets the path for a specific version of bruteforce solution."""
        return self.bruteforce_dir / f"bruteforceSolution_v{version}.cpp"

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