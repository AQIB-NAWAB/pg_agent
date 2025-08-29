#!/bin/bash

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
    MEMORY_LIMIT=$3
    RUN_FULL_SUITE=$4
    SOLUTION_FILE=$5
    EXECUTABLE_NAME=$6

    g++ -std=c++20 -O2 -w -o "${EXECUTABLE_NAME}" "${SOLUTION_FILE}" 2> compilation_error.log
    compile_exit_code=$?
    
    if [ $compile_exit_code -ne 0 ]; then
        echo "COMPILATION_FAILED"
        echo "ERROR_LOG_START"
        cat compilation_error.log
        echo "ERROR_LOG_END"
        exit 0
    fi
    echo "COMPILATION_SUCCESS"

    if ! ls -d ./*.in > /dev/null 2>&1; then
        exit 0
    fi
    
    # Create ordered list of test files following priority:
    # 1. example_*.in
    # 2. test_*.in (excluding test_edge_*)
    # 3. [0-9]*.in
    # 4. test_edge_*.in
    for infile in $(find "./" -name "example_*.in" | sort -V) \
                  $(find "./" -name "test_[0-9]*.in" | sort -V) \
                  $(find "./" -name "[0-9]*.in" | sort -V) \
                  $(find "./" -name "test_edge_*.in" | sort -V); do
        echo "INFILE: ${infile}"
        casenum=$(basename "$infile" .in)
        outfile="${casenum}.out"
        prof_file="${casenum}.prof"

        /usr/bin/time -o "${prof_file}" -f "TIME:%e MEM:%M" timeout "$TIME_LIMIT" ./"${EXECUTABLE_NAME}" < "$infile" > "$outfile"
        exit_code=$?
        
        # Write the captured exit code into the profile file
        echo "STATUS:${exit_code}" >> "${prof_file}"

        # Update the output file for special failure cases
        if [ $exit_code -eq 124 ]; then
            echo "TIMEOUT" > "$outfile"
        elif [ $exit_code -ne 0 ]; then
            echo "RUNTIME_ERROR" > "$outfile"
        fi

        if [ $exit_code -ne 0 ] && [ $RUN_FULL_SUITE = "False" ]; then
            exit 0
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