# IB-Stream Development Environment Makefile
# Sets up virtual environment, builds TWS API, and installs all packages

SHELL := /bin/bash
PYTHON := python3
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip
TWS_CLIENT_DIR := contrib/twsapi_macunix.1030.01/IBJts/source/pythonclient

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

.PHONY: help setup clean build-api install-packages test-connection dev-server

help:
	@echo "IB-Stream Development Environment"
	@echo "================================="
	@echo ""
	@echo "Available targets:"
	@echo "  setup           - Full development environment setup"
	@echo "  build-api       - Build and install TWS API from contrib/"
	@echo "  install-packages - Install ib-stream packages in development mode"
	@echo "  test-connection  - Test connection to remote gateway (requires running gateway)"
	@echo "  dev-server      - Start development server with remote gateway config"
	@echo "  clean           - Clean up virtual environment and build artifacts"
	@echo ""
	@echo "Configuration:"
	@echo "  Remote gateway configuration is in ib-stream/config/remote-gateway.env"
	@echo "  Modify IB_STREAM_HOST=192.168.0.60 to change the target host"

setup: $(VENV_DIR) build-api install-packages
	@echo -e "$(GREEN)✓ Development environment setup complete!$(NC)"
	@echo ""
	@echo "To activate the virtual environment:"
	@echo "  source $(VENV_DIR)/bin/activate"
	@echo ""
	@echo "To test remote gateway connection:"
	@echo "  make test-connection"

$(VENV_DIR):
	@echo -e "$(YELLOW)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip setuptools wheel
	@echo -e "$(GREEN)✓ Virtual environment created$(NC)"

build-api: $(VENV_DIR)
	@echo -e "$(YELLOW)Building TWS API from contrib...$(NC)"
	cd $(TWS_CLIENT_DIR) && $(PWD)/$(VENV_PYTHON) setup.py sdist bdist_wheel
	@echo -e "$(YELLOW)Installing TWS API...$(NC)"
	$(VENV_PIP) install $(TWS_CLIENT_DIR)/dist/ibapi-*.whl --force-reinstall
	@echo -e "$(GREEN)✓ TWS API built and installed$(NC)"
	@echo -e "$(YELLOW)Verifying TWS API installation...$(NC)"
	$(VENV_PYTHON) -c "from ibapi.client import EClient; print('✓ ibapi installed successfully')"

install-packages: $(VENV_DIR)
	@echo -e "$(YELLOW)Installing ib-stream packages in development mode...$(NC)"
	$(VENV_PIP) install -e ib-stream/
	$(VENV_PIP) install -e ib-studies/
	@echo -e "$(GREEN)✓ All packages installed$(NC)"

test-connection: $(VENV_DIR)
	@echo -e "$(YELLOW)Testing connection to remote gateway...$(NC)"
	@echo "Configuration: 192.168.0.60 on ports 4001,4002,7496,7497"
	@echo ""
	cd ib-stream && \
	export IB_STREAM_ENV=remote-gateway && \
	$(PWD)/$(VENV_PYTHON) -c "from src.ib_stream.config import create_config; config = create_config(); print(f'Host: {config.host}'); print(f'Ports: {config.ports}')" && \
	echo -e "$(YELLOW)Testing with a sample contract (this will fail if gateway is not running):$(NC)" && \
	timeout 10s $(PWD)/$(VENV_PYTHON) -m ib_stream.stream 265598 --number 1 --json || echo -e "$(RED)Connection failed - make sure IB Gateway is running on 192.168.0.60$(NC)"

dev-server: $(VENV_DIR)
	@echo -e "$(YELLOW)Starting development server with remote gateway configuration...$(NC)"
	cd ib-stream && \
	export IB_STREAM_ENV=remote-gateway && \
	$(PWD)/$(VENV_PYTHON) -m ib_stream.api_server

check-config: $(VENV_DIR)
	@echo -e "$(YELLOW)Current configuration:$(NC)"
	cd ib-stream && \
	export IB_STREAM_ENV=remote-gateway && \
	$(PWD)/$(VENV_PYTHON) -c "from src.ib_stream.config import create_config; config = create_config(); print(f'TWS Host: {config.host}'); print(f'TWS Ports: {config.ports}'); print(f'Server Host: {config.server_host}:{config.server_port}')"

clean:
	@echo -e "$(YELLOW)Cleaning up...$(NC)"
	rm -rf $(VENV_DIR)
	rm -rf $(TWS_CLIENT_DIR)/build/
	rm -rf $(TWS_CLIENT_DIR)/dist/
	rm -rf $(TWS_CLIENT_DIR)/ibapi.egg-info/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo -e "$(GREEN)✓ Cleanup complete$(NC)"

# Quick commands for common tasks
cli-test: $(VENV_DIR)
	@echo -e "$(YELLOW)Testing CLI tool with remote gateway...$(NC)"
	cd ib-stream && \
	export IB_STREAM_ENV=remote-gateway && \
	$(PWD)/$(VENV_PYTHON) -m ib_stream.stream 265598 --number 5 --type Last

contract-lookup: $(VENV_DIR)
	@echo -e "$(YELLOW)Testing contract lookup (uses hardcoded localhost - needs manual update)...$(NC)"
	$(VENV_PYTHON) ib-contract/contract_lookup.py AAPL

# SSH Tunnel targets
create-tunnel:
	@echo -e "$(YELLOW)Creating SSH tunnel to remote gateway...$(NC)"
	ssh -f -N -L 4002:localhost:4002 seth@192.168.0.60 && echo -e "$(GREEN)✓ SSH tunnel created: localhost:4002 -> 192.168.0.60:4002$(NC)" || echo -e "$(RED)✗ Failed to create SSH tunnel$(NC)"

test-tunnel: $(VENV_DIR)
	@echo -e "$(YELLOW)Testing connection through SSH tunnel...$(NC)"
	export IB_STREAM_ENV=ssh-tunnel && \
	timeout 15s $(VENV_PYTHON) -m ib_stream.stream 265598 --number 1 --json || echo -e "$(RED)Connection through tunnel failed$(NC)"

close-tunnel:
	@echo -e "$(YELLOW)Closing SSH tunnel...$(NC)"
	pkill -f "ssh.*-L.*4002:localhost:4002" && echo -e "$(GREEN)✓ SSH tunnel closed$(NC)" || echo -e "$(YELLOW)No tunnel found to close$(NC)"

tunnel-status:
	@echo -e "$(YELLOW)SSH tunnel status:$(NC)"
	@ps aux | grep -E "ssh.*-L.*4002" | grep -v grep || echo "No SSH tunnel found"

# Supervisor management targets
install-supervisor: $(VENV_DIR)
	@echo -e "$(YELLOW)Installing supervisor in virtual environment...$(NC)"
	$(VENV_PIP) install supervisor
	@echo -e "$(GREEN)✓ Supervisor installed$(NC)"

generate-instance-config:
	@echo -e "$(YELLOW)Generating instance-specific configuration...$(NC)"
	$(VENV_PYTHON) generate_instance_config.py

start-supervisor: install-supervisor 
	@echo -e "$(YELLOW)Starting supervisor with dynamic instance configuration...$(NC)"
	./start-supervisor.sh

supervisor-status:
	@echo -e "$(YELLOW)Supervisor status:$(NC)"
	@echo "Generated instance configuration:"
	@$(VENV_PYTHON) generate_instance_config.py | grep -E "(Client ID|HTTP Port)" | sed 's/^/  /'
	@echo ""
	./supervisor-wrapper.sh status

supervisor-start:
	@echo -e "$(YELLOW)Starting ib-stream-remote service...$(NC)"
	./supervisor-wrapper.sh start ib-stream-remote

supervisor-stop:
	@echo -e "$(YELLOW)Stopping services...$(NC)"
	./supervisor-wrapper.sh stop all

supervisor-logs:
	@echo -e "$(YELLOW)Following ib-stream-remote logs...$(NC)"
	./supervisor-wrapper.sh tail -f ib-stream-remote

supervisor-restart:
	@echo -e "$(YELLOW)Restarting ib-stream-remote service...$(NC)"
	./supervisor-wrapper.sh restart ib-stream-remote

stop-supervisor:
	@echo -e "$(YELLOW)Stopping supervisor...$(NC)"
	./supervisor-wrapper.sh shutdown

# Install just the development tools
dev-tools: $(VENV_DIR)
	$(VENV_PIP) install ruff pytest pytest-cov
	@echo -e "$(GREEN)✓ Development tools installed$(NC)"