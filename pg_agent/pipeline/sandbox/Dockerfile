
# Use a standard GCC image which has all the build tools we need.
FROM gcc:15.2.0

# Install additional dependencies including Python
RUN apt-get update && apt-get install -y \
    build-essential \
    time \
    python3 \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container.
# All commands will run from /usr/src/app.
WORKDIR /usr/src/app

# Copy the runner script
COPY runner.sh /usr/src/app/
RUN chmod +x /usr/src/app/runner.sh