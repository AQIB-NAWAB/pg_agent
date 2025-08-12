#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
# We will handle errors gracefully within the script where needed.
set -e

MODE=$1

if [ "$MODE" = "generate" ]; then
    GENERATION_ID=$2
    echo "--- Mode: GENERATE (Batch #${GENERATION_ID}) ---"
    
    echo "Compiling testcaseGenerator.cpp..."
    g++ -std=c++14 -O2 -o testcaseGenerator testcaseGenerator.cpp
    
    OUTPUT_DIR="generation${GENERATION_ID}"
    mkdir -p "$OUTPUT_DIR"
    
    cd "$OUTPUT_DIR"
    echo "Running testcaseGenerator..."
    ../testcaseGenerator
    
    echo "Test cases generated in ${OUTPUT_DIR}"

elif [ "$MODE" = "execute_suite" ]; then
    TIME_LIMIT=$2
    SOLUTION_FILE=$3 
    EXECUTABLE_NAME=$4

    echo "--- Mode: EXECUTE SUITE (Time Limit: ${TIME_LIMIT}s) ---"
    
    echo "Compiling ${SOLUTION_FILE}..."
    g++ -std=c++14 -O2 -o "${EXECUTABLE_NAME}" "${SOLUTION_FILE}"
    
    if ! ls -d *.in > /dev/null 2>&1; then
        echo "Warning: No .in files found in this directory to execute against."
        exit 0
    fi
    
    for infile in *.in; do
        casenum=$(basename "$infile" .in)
        outfile="${casenum}.out"
        prof_file="${casenum}.prof" # New file to store performance stats

        echo "Running ${EXECUTABLE_NAME} on ${infile}..."

        # We use /usr/bin/time, but direct its output to the .prof file.
        # The solution's actual stdout still goes to the .out file.
        if /usr/bin/time -o "${prof_file}" -f "TIME:%e MEM:%M STATUS:%x" \
            timeout "$TIME_LIMIT" ./"${EXECUTABLE_NAME}" < "$infile" > "$outfile"; then
            # Success Case: The command finished with exit code 0.
            echo "${infile}: SUCCESS"
        else
            # Failure Case: The command exited with a non-zero status.
            exit_code=$?
            if [ $exit_code -eq 124 ]; then
                echo "${infile}: TIMEOUT"
                echo "TIMEOUT" > "$outfile"
                # Manually write stats for TLE case
                echo "TIME:${TIME_LIMIT} MEM:0 STATUS:124" > "${prof_file}"
            else
                echo "${infile}: RUNTIME_ERROR"
                echo "RUNTIME_ERROR" > "$outfile"
                # Manually write stats for Runtime Error case
                echo "TIME:0 MEM:0 STATUS:${exit_code}" > "${prof_file}"
            fi
        fi
    done
    exit 0
    
elif [ "$MODE" = "validate_suite" ]; then
    echo "--- Mode: VALIDATE SUITE (Detailed) ---"
    echo "Compiling validator.cpp..."
    g++ -std=c++14 -O2 -o validator validator.cpp

    if ! ls -d *.in > /dev/null 2>&1; then
        echo "Warning: No .in files found to validate."
        exit 0
    fi

    # Loop through all .in files and provide detailed, parsable output
    for infile in *.in; do
        test_name=$(basename "$infile")
        echo "--- RESULT ---"
        echo "TEST_NAME:${test_name}"
        
        # We run the validator and check its exit code directly.
        # Stderr is captured to get the reason for invalid cases.
        if ./validator < "${infile}" 2> validator_error.log; then
            echo "STATUS:VALID"
        else
            REASON=$(cat validator_error.log || echo "Unknown validation error")
            echo "STATUS:INVALID"
            echo "REASON_START"
            echo "${REASON}"
            echo "REASON_END"
        fi
    done
    exit 0

else
    echo "Error: Invalid mode specified."
    exit 1
fi