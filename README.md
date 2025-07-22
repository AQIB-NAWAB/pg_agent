# LangGraph Studio – Competitive Programming Problem Generator

This repository contains a LangGraph pipeline that automatically **creates, solves, and validates competitive-programming problems**.  The code now lives inside an installable Python package (`pg_agent/`).  You can still explore it visually with **LangGraph Studio**, but you no longer need the legacy `studio/` folder.

---
## 1 . Prerequisites

• Python 3.11 or higher (the code is tested with 3.12)
• A terminal with `pip` available  
• API keys for the LLM providers you wish to use (e.g. OpenAI, Anthropic).

> **Tip:** You do **not** need to install LangChain or LangGraph globally. Everything is declared in the root-level `requirements.txt` (or `pyproject.toml`) and will be installed in the next step.

---
## 2 . Setup

### Install required packages

```bash
# 1. Clone the repo (skip if you already have it)
# git clone https://github.com/<your-org>/pg_agent.git
cd pg_agent

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv       # On MacOS you can use /opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 3. Install the pipeline dependencies (editable install recommended for dev)
pip install -r requirements.txt        # or:  pip install -e .[dev]

# 4. Provide your API keys (OpenAI, Anthropic, etc.)
# If an `.env.example` file exists, copy it over and fill in your keys:
# cp .env.example .env
# then edit .env and fill in the keys, e.g.
# OPENAI_API_KEY="sk-..."
# ANTHROPIC_API_KEY="sk-anthropic-..."
```

### Install docker

Install docker using any common guide.

Additional dependencies on MacOS:
```
brew install docker-credential-helper
```
Check your ~/.docker/config.json and replace "credsStore" by "credStore":
```
sed -i 's/"credsStore"/"credStore"/g' ~/.docker/config.json
```
Add docker cli path:
```
echo 'export PATH="$HOME/.docker/bin:$PATH"' >> ~/.zshrc
```


---
## 3 . Command-line tools

The package provides several command-line tools for generating and managing competitive programming problems. Each tool accepts an optional `problem_dir` argument. If not specified, the default directory is read from `pg_agent_settings.json`:

```json
{
    "problem_directory": "../problems/generated_problem",
    // ... other settings ...
}
```

You can modify this setting to change the default problem directory for all tools.

### 3.1 Problem Statement Generator (`01_problem_statement.py`)

Creates or refines a programming problem statement.

```bash
python 01_problem_statement.py [output_dir] [options]
  --topics TOPICS     Create from random/specified topics (comma-separated)
  --idea IDEA        Create from an initial problem concept
  --refine FEEDBACK  Refine existing problem with feedback
  --original PATH    Use another problem as inspiration
  --verbose         Enable verbose logging
```

### 3.2 Manual Test Generator (`02_manual_tests.py`)

Generates basic test cases for an existing problem.

```bash
python 02_manual_tests.py [problem_dir] [options]
  --verbose         Enable verbose logging
  --parse          Parse tests from latest raw response
```

### 3.3 Bruteforce Solution Generator (`03_bruteforce_sol.py`)

Generates or refines a bruteforce solution for the problem.

```bash
python 03_bruteforce_sol.py [problem_dir] [options]
  --refine [FEEDBACK]  Refine previous solution with optional feedback
  --log-level LEVEL   Set logging level (debug/info/warning/error/critical)
  --quiet            Suppress all output except errors
```

### 3.4 Optimal Solution Generator (`04_optimal_sol.py`)

Generates or refines an optimized solution for the problem.

```bash
python 04_optimal_sol.py [problem_dir] [options]
  --refine [FEEDBACK]  Refine previous solution with feedback
  --time-limit SEC    Time limit for solution execution (default: 5s)
  --log-level LEVEL   Set logging level
  --quiet            Suppress all output except errors
```

### 3.5 Test Generator (`05_test_generator.py`)

Generates comprehensive test cases and validators.

```bash
python 05_test_generator.py [problem_dir] [options]
  --mode MODE        Generation mode: basic/edge/validator/all (default: basic)
  --refine FEEDBACK  Refine existing generator/validator
  --log-level LEVEL  Set logging level
  --quiet           Suppress all output except errors
```

### 3.6 Test Suite Runner (`06_test_suite.py`)

Validates test cases and generates outputs using bruteforce/optimal solutions.

```bash
python 06_test_suite.py [problem_dir] [options]
  --mode MODE        Operation mode: validator/outputs (default: outputs)
  --time-limit SEC   Time limit for solution execution (default: 2s)
  --use-optimal     Use optimal solution instead of bruteforce
  --log-level LEVEL  Set logging level
  --quiet           Suppress all output except errors
```

### Typical Workflow

1. Generate problem statement: `python 01_problem_statement.py`
2. Create manual test cases: `python 02_manual_tests.py`
3. Generate bruteforce solution: `python 03_bruteforce_sol.py`
4. Generate optimal solution: `python 04_optimal_sol.py`
5. Generate comprehensive tests: `python 05_test_generator.py --mode all`
6. Validate and generate outputs: `python 06_test_suite.py`

---
## 4 . Launching LangGraph Studio (might be used in future, major flow right now is command line)

```bash
# First time only — install your *local* package in editable mode so Studio can
# import it as a proper Python package (no need to repeat after each change):
pip install -e .

# Quick dev server (hot-reload):
langgraph dev 
```

This will start a local web server on `http://localhost:2024/` (the exact port is shown in the terminal). Open the URL in your browser to:

* Visualise the full pipeline graph
* Inspect node inputs/outputs
* Execute the pipeline end-to-end or step-by-step
* Monitor the conversation state live

> **Note:** The first run may take a little longer because the LLMs have to spin up.

If you just want to run the pipeline headless:

```bash
python -m pg_agent.pipeline.pipeline_graph   # runs __main__ section
python - <<'PY'
from pg_agent.pipeline import test_pipeline
print(test_pipeline().invoke({}))
PY
```

---
## 5 . Troubleshooting

| Symptom | Fix |
|---------|------|
| `ModuleNotFoundError` for LangGraph / LangChain | Check that you installed dependencies from **requirements.txt** inside the active virtualenv. |
| Browser shows blank Studio page | Verify the terminal shows `Uvicorn running on ...` and nothing crashed. Refresh. |
| "401 / 403" from provider | Double-check `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. |

---
## 6 . Contributing

PRs are welcome! Please open an issue first to discuss changes.

---
## 7 . License

MIT © 2024 