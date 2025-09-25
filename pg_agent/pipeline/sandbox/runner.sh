#!/bin/bash

MODE=$1

if [ "$MODE" = "generate" ]; then
    LANGUAGE=${2:-"C++"}  # Default to C++ if not provided
    echo "--- Mode: GENERATE ($LANGUAGE) ---"
    
    if [ "$LANGUAGE" = "C++" ]; then
        echo "Compiling generator.cpp..."
        g++ -std=c++20 -O2 -o generator generator.cpp
        
        echo "Running generator..."
        ./generator
    elif [ "$LANGUAGE" = "Python" ]; then
        echo "Running Python generator..."
        python3 generator.py
    else
        echo "Unsupported language: $LANGUAGE"
        exit 1
    fi
    
    echo "Test cases generated in current directory"

elif [ "$MODE" = "execute_suite" ]; then
    TIME_LIMIT=$2
    MEMORY_LIMIT=$3
    RUN_FULL_SUITE=$4
    SOLUTION_FILE=$5
    EXECUTABLE_NAME=$6
    LANGUAGE=${7:-"C++"}  # Default to C++ if not provided

    if [ "$LANGUAGE" = "C++" ]; then
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
    elif [ "$LANGUAGE" = "Python" ]; then
        # For Python, just check if the file exists and is valid
        if [ ! -f "${SOLUTION_FILE}" ]; then
            echo "COMPILATION_FAILED"
            echo "ERROR_LOG_START"
            echo "Python file not found: ${SOLUTION_FILE}"
            echo "ERROR_LOG_END"
            exit 0
        fi
        
        # Basic syntax check
        python3 -m py_compile "${SOLUTION_FILE}" 2> compilation_error.log
        compile_exit_code=$?
        
        if [ $compile_exit_code -ne 0 ]; then
            echo "COMPILATION_FAILED"
            echo "ERROR_LOG_START"
            cat compilation_error.log
            echo "ERROR_LOG_END"
            exit 0
        fi
        echo "COMPILATION_SUCCESS"
    else
        echo "COMPILATION_FAILED"
        echo "ERROR_LOG_START"
        echo "Unsupported language: ${LANGUAGE}"
        echo "ERROR_LOG_END"
        exit 0
    fi

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
                  $(find "./" -name "test_small_[0-9]*.in" | sort -V) \
                  $(find "./" -name "test_medium_[0-9]*.in" | sort -V) \
                  $(find "./" -name "test_large_[0-9]*.in" | sort -V) \
                  $(find "./" -name "test_edge_[0-9]*.in" | sort -V) \
                  $(find "./" -name "[0-9]*.in" | sort -V) ; do
        echo "INFILE: ${infile}"
        casenum=$(basename "$infile" .in)
        outfile="${casenum}.out"
        prof_file="${casenum}.prof"

        if [ "$LANGUAGE" = "C++" ]; then
            /usr/bin/time -o "${prof_file}" -f "TIME:%e MEM:%M" timeout "$TIME_LIMIT" ./"${EXECUTABLE_NAME}" < "$infile" > "$outfile"
        elif [ "$LANGUAGE" = "Python" ]; then
            /usr/bin/time -o "${prof_file}" -f "TIME:%e MEM:%M" timeout "$TIME_LIMIT" python3 "${SOLUTION_FILE}" < "$infile" > "$outfile"
        fi
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
    LANGUAGE=${2:-"C++"}  # Default to C++ if not provided
    echo "--- Mode: VALIDATE SUITE ($LANGUAGE) (Detailed) ---"
    
    if [ "$LANGUAGE" = "C++" ]; then
        echo "Compiling validator.cpp..."
        g++ -std=c++14 -O2 -o validator validator.cpp
        VALIDATOR_CMD="./validator"
    elif [ "$LANGUAGE" = "Python" ]; then
        echo "Using Python validator..."
        VALIDATOR_CMD="python3 validator.py"
    else
        echo "Unsupported language: $LANGUAGE"
        exit 1
    fi

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
        if $VALIDATOR_CMD < "${infile}" 2> validator_error.log; then
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