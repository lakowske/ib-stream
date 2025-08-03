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

.PHONY: help setup clean build-api install-packages test-connection dev-tools

help:
	@echo "IB-Stream Development Environment"
	@echo "================================="
	@echo ""
	@echo "Core Setup:"
	@echo "  setup              - Full development environment setup"
	@echo "  build-api          - Build and install TWS API from contrib/"
	@echo "  install-packages   - Install ib-util and ib-stream packages in development mode"
	@echo "  dev-tools          - Install development tools (ruff, pytest, click)"
	@echo "  clean              - Clean up virtual environment and build artifacts"
	@echo ""
	@echo "New Configuration System (v2):"
	@echo "  config-validate       - Validate new configuration system"
	@echo "  config-show           - Show current configuration for both services"
	@echo "  config-test-new-system - End-to-end test of new configuration"
	@echo "  test-connection-v2    - Test connection using new configuration"
	@echo "  contract-lookup-v2    - Test contract lookup with new configuration"
	@echo "  start-supervisor-v2   - Start supervisor with new configuration"
	@echo ""
	@echo "Supervisor Management:"
	@echo "  start-supervisor      - Start supervisor with instance configuration"
	@echo "  supervisor-status     - Show supervisor and instance status"
	@echo "  supervisor-logs       - Follow ib-stream-remote logs"
	@echo "  supervisor-stop       - Stop all services"
	@echo "  stop-supervisor       - Stop supervisor daemon"
	@echo ""
	@echo "Advanced Features:"
	@echo "  config-watch          - Watch all configuration files for changes (hot-reload)"
	@echo "  config-watch-stream   - Watch ib-stream configuration only"
	@echo "  config-watch-contract - Watch ib-contract configuration only"
	@echo "  config-diff           - Configuration comparison and analysis tool"
	@echo "  config-diff-summary   - Show configuration summary for all services"
	@echo "  config-diff-compare   - Compare ib-stream vs ib-contract configurations"
	@echo ""
	@echo "Legacy Targets (deprecated):"
	@echo "  test-connection-legacy - Test connection using legacy configuration"
	@echo "  start-production-legacy - Start production using old system"
	@echo ""
	@echo "Configuration:"
	@echo "  New system uses ib-stream/config/*.env files with type-safe validation"
	@echo "  Instance configuration is auto-generated to avoid port/client ID conflicts"

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
	@echo -e "$(YELLOW)Installing ib-util and ib-stream packages in development mode...$(NC)"
	$(VENV_PIP) install -e ib-util/
	$(VENV_PIP) install -e ib-stream/
	$(VENV_PIP) install -e ib-studies/
	@echo -e "$(YELLOW)Verifying ib-util installation...$(NC)"
	$(VENV_PYTHON) -c "from ib_util import IBConnection; print('✓ ib-util installed successfully')"
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

# Production server configuration targets
start-production: 
	@echo -e "$(YELLOW)Starting production server configuration...$(NC)"
	@echo "This will run ib-stream on the production server with localhost TWS connection"
	@echo "and full storage enabled for continuous market data recording."
	@echo ""
	./start-production.sh

test-production-connection:
	@echo -e "$(YELLOW)Testing production server connection (localhost)...$(NC)"
	@echo "Configuration: localhost on port 4002"
	@echo ""
	cd ib-stream && \
	export IB_STREAM_ENV=production-server && \
	$(VENV_PYTHON) -c "from src.ib_stream.config import create_config; config = create_config(); print(f'Host: {config.host}'); print(f'Ports: {config.ports}'); print(f'Storage: {config.storage.enable_storage}')" && \
	echo -e "$(YELLOW)Testing with a sample contract:$(NC)" && \
	timeout 10s $(VENV_PYTHON) -m ib_stream.stream 265598 --number 1 --json || echo -e "$(RED)Connection failed - check local TWS Gateway$(NC)"

production-status:
	@echo -e "$(YELLOW)Production Server Status:$(NC)"
	@echo "Server: 192.168.0.60 (localhost connection)"
	@echo "Environment: production-server"
	@echo ""
	make supervisor-status
	@echo ""
	@echo -e "$(YELLOW)Storage status:$(NC)"
	@ls -la storage/ 2>/dev/null | head -5 || echo "Storage directory not found"

# Install just the development tools
dev-tools: $(VENV_DIR)
	$(VENV_PIP) install ruff pytest pytest-cov click watchdog
	@echo -e "$(GREEN)✓ Development tools installed$(NC)"

# New Configuration Management System (v2)
.PHONY: config-validate config-show config-test-new-system config-migrate test-connection-v2 contract-lookup-v2 start-supervisor-v2 config-watch config-watch-stream config-watch-contract config-diff config-diff-summary config-diff-compare

config-validate: dev-tools
	@echo -e "$(YELLOW)Validating new configuration system...$(NC)"
	$(VENV_PYTHON) -c "from ib_util.config.compat import validate_migration; import json; result = validate_migration(); print(json.dumps(result, indent=2)); exit(0 if result['valid'] else 1)"

config-show: dev-tools  
	@echo -e "$(YELLOW)Current configuration (new system):$(NC)"
	@echo ""
	@echo "ib-stream configuration:"
	$(VENV_PYTHON) -c "from ib_stream.config_v2 import create_config; config = create_config(); print(f'  Host: {config.host}'); print(f'  Client ID: {config.client_id}'); print(f'  Server Port: {config.server_port}'); print(f'  Storage: {config.storage.enable_storage}')"
	@echo ""
	@echo "ib-contract configuration:"
	$(VENV_PYTHON) ib-contract/config_v2.py | grep -E "(Host:|Client ID:|Server Port:)" | sed 's/^/  /'

config-test-new-system: dev-tools
	@echo -e "$(YELLOW)Testing new configuration system end-to-end...$(NC)"
	@echo ""
	@echo "1. Testing ib-stream configuration:"
	cd ib-stream && $(PWD)/$(VENV_PYTHON) -c "from src.ib_stream.app_lifecycle import get_app_state; app_state = get_app_state(); config = app_state['config']; print(f'  ✓ Host: {config.host}'); print(f'  ✓ Client ID: {config.client_id}'); print(f'  ✓ Server Port: {config.server_port}'); print(f'  ✓ Storage: {config.storage.enable_storage}'); print(f'  ✓ Tracked Contracts: {len(config.storage.tracked_contracts) if hasattr(config.storage, \"tracked_contracts\") and config.storage.tracked_contracts else 0}')"
	@echo ""
	@echo "2. Testing ib-contract configuration:"
	$(VENV_PYTHON) ib-contract/config_v2.py | head -8 | grep -E "(Service:|Host:|Client ID:|Server Port:)" | sed 's/^/  ✓ /'
	@echo ""
	@echo -e "$(GREEN)✓ New configuration system is working correctly!$(NC)"

# Updated targets that use the new configuration system
test-connection-v2: dev-tools
	@echo -e "$(YELLOW)Testing connection with new configuration system...$(NC)"
	@echo "Using production server configuration (localhost on port 4002)"
	@echo ""
	cd ib-stream && \
	$(PWD)/$(VENV_PYTHON) -c "from src.ib_stream.app_lifecycle import get_app_state; app_state = get_app_state(); config = app_state['config']; print(f'Host: {config.host}'); print(f'Ports: {config.ports}'); print(f'Client ID: {config.client_id}'); print(f'Storage: {config.storage.enable_storage}')" && \
	echo -e "$(YELLOW)Testing with a sample contract (this will fail if gateway is not running):$(NC)" && \
	timeout 10s $(PWD)/$(VENV_PYTHON) -m ib_stream.stream 265598 --number 1 --json || echo -e "$(RED)Connection failed - make sure IB Gateway is running locally$(NC)"

contract-lookup-v2: dev-tools
	@echo -e "$(YELLOW)Testing contract lookup with new configuration...$(NC)"
	$(VENV_PYTHON) ib-contract/contract_lookup.py AAPL

# Supervisor management with new configuration
start-supervisor-v2: install-supervisor generate-instance-config
	@echo -e "$(YELLOW)Starting supervisor with new configuration system...$(NC)"
	@echo "This uses the new configuration compatibility layer"
	./start-supervisor.sh

# Advanced Features
config-watch: dev-tools
	@echo -e "$(YELLOW)Starting configuration hot-reload watcher...$(NC)"
	@echo "Edit .env files in ib-stream/config/ to see real-time configuration changes"
	@echo "Press Ctrl+C to stop watching"
	@echo ""
	$(VENV_PYTHON) config-watch.py

config-watch-stream: dev-tools
	@echo -e "$(YELLOW)Watching ib-stream configuration only...$(NC)"
	$(VENV_PYTHON) config-watch.py --service ib-stream

config-watch-contract: dev-tools
	@echo -e "$(YELLOW)Watching ib-contract configuration only...$(NC)"
	$(VENV_PYTHON) config-watch.py --service ib-contract

config-diff: dev-tools
	@echo -e "$(YELLOW)Configuration comparison and analysis tool$(NC)"
	@echo "Usage examples:"
	@echo "  make config-diff-summary  - Show configuration summary"
	@echo "  make config-diff-compare  - Compare ib-stream vs ib-contract"
	@echo "  $(VENV_PYTHON) config-diff.py --help  - Full help"
	@echo ""
	$(VENV_PYTHON) config-diff.py summary

config-diff-summary: dev-tools
	@echo -e "$(YELLOW)Configuration summary for all services:$(NC)"
	$(VENV_PYTHON) config-diff.py summary

config-diff-compare: dev-tools
	@echo -e "$(YELLOW)Comparing ib-stream vs ib-contract configurations:$(NC)"
	$(VENV_PYTHON) config-diff.py compare ib-stream ib-contract

# Legacy targets (deprecated but kept for compatibility)
start-production-legacy: 
	@echo -e "$(YELLOW)WARNING: Using legacy configuration system$(NC)"
	@echo "Consider migrating to: make start-supervisor-v2"
	$(MAKE) start-production

test-connection-legacy: 
	@echo -e "$(YELLOW)WARNING: Using legacy configuration system$(NC)"
	@echo "Consider migrating to: make test-connection-v2"
	$(MAKE) test-connection