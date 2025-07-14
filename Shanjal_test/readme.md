**To execute the testing and generating for 16 cpp solutions**

1. go into the Shanjal_test folder
2. run the command "langgraph dev --allow-blocking" (in order to generate the parallel executions without any blockage)
3. for testing the 16 cpp solutions over all the test cases files (50-70) we have to use the **problem_gen** graph (please make sure to include all the testcases files 1.in, 1.out, 2.in, 2.out ...... inside the TEST_CASES folder in order to test all the testcases and problem.md to load the problem).
4. Once it get done it will create two files final_results.json (which stores the all the testcases pass, failed and timedout and description for all 16 cpp iteration for each of the testcases) and second is summary.json which will give the summary about the number of testcases passed, failed and timedout.
5. for generating the 16 cpp solution please switch to the **problem generator** and it will save the problem.md and all the 16 cpp solutions into the qwen folder.