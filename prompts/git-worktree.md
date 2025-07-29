# Git Worktree Creation Prompt

You are an expert Git and development environment management assistant. Your task is to create a new git worktree with automatic numbering and set up the development environment.

## Task Overview

Create a new git worktree using the project naming pattern `{project-name}-{number}` where the number is automatically determined by checking existing worktrees in the parent directory.

## Prerequisites

Before starting, ensure the following requirements are met:

1. **Directory Access**: If Claude Code restricts parent directory access, run:
   ```
   /add-dir ../
   ```

2. **Verify Git Repository**: Ensure you're in a git repository:
   ```bash
   git rev-parse --show-toplevel
   ```

3. **Check Current Location**: Verify you're in the correct project directory:
   ```bash
   pwd
   ```

## Step-by-Step Instructions

### 1. Determine Current Project Information

- Extract the current project name from the current directory name (e.g., if in `ib-stream-1`, the project name is `ib-stream`)
- Identify the current directory's parent directory where sibling worktrees would be located

### 2. Scan for Existing Worktrees

**Important**: Use simple, sequential commands instead of complex one-liners to avoid shell escaping issues.

- Check the parent directory for existing directories that match the pattern `{project-name}-{number}`
- Parse the numbers from existing worktree directory names
- Find the highest existing number
- Calculate the next available number (highest + 1, or 1 if no existing worktrees found)

Use this ultra-simplified approach to avoid shell complexity:
```bash
# List existing worktrees
echo "Scanning for existing worktrees..."
ls -1d ../ib-stream-* 2>/dev/null || echo "No existing worktrees found"

# Manually determine next number based on what you see
# This is more reliable than complex shell variable assignments
# Example: if you see ib-stream-1, ib-stream-2, then use NEXT_NUM=3
NEXT_NUM=3  # Update this based on the ls output above

echo "Next worktree number: $NEXT_NUM"
```

**Note**: Due to Claude Code shell escaping limitations, manually setting `NEXT_NUM` based on the `ls` output is more reliable than complex variable assignments.

### 3. Create the New Worktree

- Use `git worktree add` to create a new worktree in the parent directory
- Name the new worktree directory using the calculated number
- Git will automatically create a new branch to avoid conflicts with existing worktrees

Use this approach:
```bash
# Create the new worktree with automatic branch creation
echo "Creating new worktree: ib-stream-$NEXT_NUM"
git worktree add ../ib-stream-$NEXT_NUM -b ib-stream-$NEXT_NUM-branch main

# Navigate to the new worktree
cd ../ib-stream-$NEXT_NUM

# Verify location and branch
echo "✓ Current location: $(pwd)"
echo "✓ Git branch: $(git branch --show-current)"
```

### 4. Set Up Development Environment

- Navigate to the new worktree directory
- Use the project's Makefile `setup` target which performs:
  - Creates `.venv` virtual environment
  - Builds and installs TWS API from `contrib/` directory
  - Installs ib-util, ib-stream, and ib-studies packages in development mode
  - Verifies all installations are working correctly
- Run `make setup` to complete the full development environment setup

**Note**: The updated Makefile now automatically installs ib-util, eliminating the need for manual package verification tests.

### 5. Service Setup and Health Verification

Generate instance configuration and start services to verify complete functionality:

```bash
# Step 5a: Generate instance-specific configuration
echo "Generating instance configuration..."
make generate-instance-config

# Step 5b: Start services using supervisor
echo "Starting services..."
make start-supervisor

# Step 5c: Check service status
echo "Checking service status..."
make supervisor-status

# Step 5d: Wait for services to fully start (give them a moment)
echo "Waiting for services to initialize..."
sleep 5

# Step 5e: Health check both services
echo "Performing health checks..."

# Get the ports from the instance config
STREAM_PORT=$(python -c "import sys; sys.path.append('ib-stream/src'); from ib_stream.config import create_config; print(create_config().server_port)" 2>/dev/null || echo "8096")
CONTRACTS_PORT=$((STREAM_PORT + 10))

echo "Testing ib-stream health on port $STREAM_PORT..."
curl -s http://localhost:$STREAM_PORT/health | head -1 | grep -q "healthy" && echo "✓ ib-stream service healthy" || echo "✗ ib-stream service not responding"

echo "Testing ib-contracts health on port $CONTRACTS_PORT..."
curl -s http://localhost:$CONTRACTS_PORT/health | head -1 | grep -q "healthy" && echo "✓ ib-contracts service healthy" || echo "✗ ib-contracts service not responding"

# Step 5f: Verification summary
echo ""
echo "✓ New worktree created at: $(pwd)"
echo "✓ Git branch: $(git branch --show-current)"
echo "✓ Development environment set up with make setup"
echo "✓ Services started with supervisor"
echo ""
echo "To activate virtual environment:"
echo "  source .venv/bin/activate"
echo ""
echo "Service endpoints:"
echo "  ib-stream: http://localhost:$STREAM_PORT/"
echo "  ib-contracts: http://localhost:$CONTRACTS_PORT/"
echo ""
echo "Management commands:"
echo "  make supervisor-status  - Check service status"
echo "  make supervisor-logs    - View service logs"
echo "  make supervisor-stop    - Stop all services"
```

## Example Commands to Generate

Based on the current directory `ib-stream-1`, you should generate commands using the simplified approach:

```bash
# Step 1: Verify prerequisites
pwd
git rev-parse --show-toplevel

# Step 2: Scan for existing worktrees (ultra-simplified)
echo "Scanning for existing worktrees..."
ls -1d ../ib-stream-* 2>/dev/null || echo "No existing worktrees found"

# Manually set next number based on ls output above
NEXT_NUM=3  # Update this number based on what you see

echo "Next worktree number: $NEXT_NUM"

# Step 3: Create new worktree with branch
echo "Creating new worktree: ib-stream-$NEXT_NUM"
git worktree add ../ib-stream-$NEXT_NUM -b ib-stream-$NEXT_NUM-branch main

# Step 4: Navigate and set up environment
cd ../ib-stream-$NEXT_NUM
echo "✓ Current location: $(pwd)"
echo "✓ Git branch: $(git branch --show-current)"

echo "Setting up development environment..."
make setup

# Step 5: Service setup and health verification
echo "Generating instance configuration..."
make generate-instance-config

echo "Starting services..."
make start-supervisor

echo "Checking service status..."
make supervisor-status

echo "Waiting for services to initialize..."
sleep 5

echo "Performing health checks..."
STREAM_PORT=$(python -c "import sys; sys.path.append('ib-stream/src'); from ib_stream.config import create_config; print(create_config().server_port)" 2>/dev/null || echo "8096")
CONTRACTS_PORT=$((STREAM_PORT + 10))

echo "Testing ib-stream health on port $STREAM_PORT..."
curl -s http://localhost:$STREAM_PORT/health | head -1 | grep -q "healthy" && echo "✓ ib-stream service healthy" || echo "✗ ib-stream service not responding"

echo "Testing ib-contracts health on port $CONTRACTS_PORT..."
curl -s http://localhost:$CONTRACTS_PORT/health | head -1 | grep -q "healthy" && echo "✓ ib-contracts service healthy" || echo "✗ ib-contracts service not responding"

echo ""
echo "✓ New worktree created at: $(pwd)"
echo "✓ Git branch: $(git branch --show-current)"
echo "✓ Development environment set up with make setup"
echo "✓ Services started with supervisor"
echo ""
echo "Service endpoints:"
echo "  ib-stream: http://localhost:$STREAM_PORT/"
echo "  ib-contracts: http://localhost:$CONTRACTS_PORT/"
echo ""
echo "Management commands:"
echo "  make supervisor-status  - Check service status"
echo "  make supervisor-logs    - View service logs"
echo "  make supervisor-stop    - Stop all services"
```

## Common Issues and Troubleshooting

### Directory Access Issues
- **Problem**: `cd ..` or parent directory access blocked
- **Solution**: Run `/add-dir ../` to add parent directory to allowed paths

### Git Repository Issues  
- **Problem**: "fatal: not a git repository"
- **Solution**: Ensure you're running from within the git repository directory
- **Check**: Run `git rev-parse --show-toplevel` to verify git repository

### Branch Conflicts
- **Problem**: "branch 'main' is already used by worktree"  
- **Solution**: Use `-b` flag to create a new branch (already included in improved commands)

### Setup Failures
- **Problem**: `make setup` fails
- **Solutions**:
  - Check that `contrib/` directory exists with TWS API
  - Verify `Makefile` exists in the new worktree
  - Run `make help` to see available targets
  - Check for Python virtual environment issues

### Service Startup Failures
- **Problem**: Services fail with "ModuleNotFoundError: No module named 'ib_util'"
- **Solution**: The updated Makefile should install ib-util automatically with `make setup`
- **Alternative**: Manually install if needed: `.venv/bin/pip install -e ib-util/`

### Service Health Check Failures
- **Problem**: Health checks fail or services don't respond
- **Solutions**:
  - Check supervisor status: `make supervisor-status`
  - View service logs: `make supervisor-logs`
  - Restart services: `./supervisor-wrapper.sh restart all`
  - Verify IB Gateway is running and accessible
  - Check for port conflicts (each worktree gets unique ports)

### Shell Complexity Issues
- **Problem**: Complex bash commands fail with syntax errors
- **Solution**: Use the simplified, step-by-step commands provided in this prompt
- **Avoid**: Nested `$()` expansions and complex one-liners

### Verification Failures
- **Problem**: TWS API or packages not installed correctly
- **Solutions**:
  - Check `.venv/bin/python -c "from ibapi.client import EClient"` output
  - Verify `contrib/twsapi_macunix.1030.01/IBJts/source/pythonclient` exists  
  - Re-run `make setup` if needed

## Output Format

Provide the exact bash commands to run, with clear explanations of what each command does. Use the simplified, step-by-step approach outlined in this prompt to avoid shell complexity issues.

## Special Considerations

- **Claude Code Environment**: Account for directory access restrictions and shell escaping limitations
- **Error Resilience**: Use simple commands that are less likely to fail due to shell complexity
- **Sequential Execution**: Break complex operations into separate, verifiable steps
- **Branch Management**: Always create a new branch to avoid worktree conflicts
- **Comprehensive Verification**: Include thorough checks to ensure successful setup
- **Directory Structure**: Ensure the new worktree is created in the same parent directory as the current worktree
- **Numbering**: Account for potential gaps in numbering (e.g., if ib-stream-1 and ib-stream-3 exist, create ib-stream-4)

## Success Criteria

- New worktree created with correct incremental numbering
- Development environment fully set up using `make setup`
- Virtual environment created with all dependencies installed
- TWS API built and installed from contrib/ directory
- ib-util, ib-stream and ib-studies packages installed in development mode
- Instance configuration generated with unique ports and client IDs
- Both ib-stream and ib-contracts services started via supervisor
- Health checks pass for both services (return "healthy" status)
- Service endpoints accessible and responding correctly
- Clear instructions provided for service management and development workflow

## Implementation Notes

When following this prompt:

1. **Start with Prerequisites**: Always check directory access and git repository status first
2. **Use Simple Commands**: Avoid complex shell constructs that may fail in Claude Code environment  
3. **Verify Each Step**: Check the output of each major step before proceeding
4. **Handle Branch Creation**: Use the `-b` flag to create new branches automatically
5. **Comprehensive Testing**: Run all verification steps to ensure complete setup

Execute this task by analyzing the current environment and generating the appropriate commands using the simplified, error-resistant approach outlined above.