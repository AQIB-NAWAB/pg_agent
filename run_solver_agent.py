import os
<<<<<<< HEAD
import sys
import uuid # Import the uuid library
=======
>>>>>>> 3d60c04 (auto agent basic flow)
from dotenv import load_dotenv
from pg_agent.auto_solver_agent.graph import auto_solver_graph
from pg_agent.auto_solver_agent.schemas import SolverState

<<<<<<< HEAD
load_dotenv()

if not os.getenv("ANTHROPIC_API_KEY"):
    print("FATAL ERROR: ANTHROPIC_API_KEY not found in .env file or environment.")
    sys.exit(1)

# PROBLEM_STATEMENT = """
# Write a C++ program that solves the "Two Sum" problem.
# Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.
# You may assume that each input would have exactly one solution, and you may not use the same element twice.
# You can return the answer in any order.
# Input Format:
# The first line contains an integer `n`, the number of elements in the array.
# The second line contains `n` space-separated integers.
# The third line contains the integer `target`.
# Output Format:
# Print the two indices (0-based) separated by a space.
# """

PROBLEM_STATEMENT = """
E. Unpleasant Strings

time limit per test: 2 seconds
memory limit per test: 512 megabytes

Let's call a letter allowed if it is a lowercase letter and is one of the first k letters of the Latin alphabet.

You are given a string s of length n, consisting only of allowed letters.

Let's call a string t pleasant if t is a subsequence of s.

You are given q strings t1,t2,…,tq. All of them consist only of allowed letters. For each string t[i]
, calculate the minimum number of allowed letters you need to append to it on the right so that it stops being pleasant.

A sequence t is a subsequence of a sequence s if t can be obtained from s
by the deletion of several (possibly, zero or all) element from arbitrary positions.

Input
The first line contains two integers n and k
(1≤n≤10**6; 1≤k≤26) — the length of the string s
 and the number of allowed letters.

The second line contains the string s, consisting of n
 lowercase Latin letters. Each character of the string is one of the first k
 letters of the Latin alphabet.

The third line contains one integer q
 (1≤q≤2⋅10**5) — the number of queries.

The next q lines contain queries: one query per line. The i-th line contains the string ti
, consisting only of allowed letters.

Additional constraint on input: the total length of all t[i] does not exceed 10**6.

Output
For each query, output one integer — the minimum number of allowed letters that need to be appended to the string on the right so that it stops being pleasant.

Examples
Input
7 3
abacaba
3
cc
bcb
b


Output
0
1
2


Input
5 1
aaaaa
6
a
aa
aaa
aaaa
aaaaa
aaaaaa


Output
5
4
3
2
1
0

Note
In the first example:

The string cc is already unpleasant, so nothing needs to be appended to it;
bcb is pleasant, so at least one letter needs to be appended to the right: bcba will not work, but bcbb and bcbc are unpleasant.
To b, at least two letters need to be appended, since ba, bb, and bc are pleasant. For example, we can obtain an unpleasant string bbb.
"""


def main():
    """Main function to run the auto-solver agent."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"Starting a new run with ID: {run_id}")
    
    initial_state: SolverState = {
        "problem_statement": PROBLEM_STATEMENT.strip(),
        "num_test_generations": 1,
        "max_iterations": 5,
        "run_id": run_id,
        "bruteforce_time_limit": 5.0,  # <-- Set the time limit in seconds here
        "bruteforce_code": None,
        "test_generator_code": None,
        "solution_code": None,
        "test_cases_dir_path": None,
=======
# --- Load Environment Variables ---
print("Attempting to load .env file...")
load_dotenv()
print(".env file loaded (if it exists).")

# --- DEBUGGING CHECK ---
# We will now check if the environment variable was loaded successfully.
api_key = os.getenv("ANTHROPIC_API_KEY")
print("\n--- API Key Check ---")
if api_key:
    # For security, we only print the first few and last few characters.
    print(f"SUCCESS: Anthropic API Key found. It starts with '{api_key[:5]}' and ends with '{api_key[-4:]}'.")
else:
    print("FAILURE: Anthropic API Key was NOT found in the environment.")
    print("Please check the following:")
    print("1. Is the .env file in the same directory as this script?")
    print("2. Is the variable name exactly ANTHROPIC_API_KEY in the .env file?")
    print("3. Did you save the .env file?")
    # We exit here because the script is guaranteed to fail without the key.
    exit() # Stop the script
print("---------------------\n")


# --- Define the problem to solve ---
PROBLEM_STATEMENT = """
Write a C++ program that solves the "Two Sum" problem.
Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.
You may assume that each input would have exactly one solution, and you may not use the same element twice.
You can return the answer in any order.
Input Format:
The first line contains an integer `n`, the number of elements in the array.
The second line contains `n` space-separated integers.
The third line contains the integer `target`.
Output Format:
Print the two indices (0-based) separated by a space.
"""

def main():
    """Main function to run the auto-solver agent."""
    
    initial_state: SolverState = {
        "problem_statement": PROBLEM_STATEMENT.strip(),
        "num_test_generations": 3,
        "max_iterations": 5,
        "bruteforce_code": None,
        "test_generator_code": None,
        "solution_code": None,
>>>>>>> 3d60c04 (auto agent basic flow)
        "test_results": None,
        "iteration_count": 0,
        "final_verdict": "PENDING",
    }
    
    print("--- Invoking Auto-Solver Agent ---")
    
    for event in auto_solver_graph.stream(initial_state):
        node_name = list(event.keys())[0]
        print(f"\n--- Finished Node: {node_name} ---")
    
    print("\n--- Agent Finished ---")

if __name__ == "__main__":
    main()