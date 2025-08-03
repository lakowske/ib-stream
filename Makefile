# IB-Stream Build Automation Makefile
# Focuses on environment setup, TWS API building, and package installation
# For service management and configuration, use: python ib.py

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

.PHONY: help setup clean build-api install-packages dev-tools

help:
	@echo "IB-Stream Build Automation"
	@echo "=========================="
	@echo ""
	@echo "Build & Environment Setup:"
	@echo "  setup              - Full development environment setup"
	@echo "  build-api          - Build and install TWS API from contrib/"
	@echo "  install-packages   - Install ib-util and ib-stream packages in development mode"
	@echo "  dev-tools          - Install development tools (ruff, pytest, click)"
	@echo "  clean              - Clean up virtual environment and build artifacts"
	@echo ""
	@echo "Service Management & Configuration:"
	@echo "  For all service operations, configuration management, and development workflows:"
	@echo "  Use the CLI tool: python ib.py --help"
	@echo ""
	@echo "Quick Start:"
	@echo "  make setup                    # Set up environment"
	@echo "  python ib.py services start  # Start services"
	@echo "  python ib.py services status # Check status"
	@echo "  python ib.py test connection # Test connection"

setup: $(VENV_DIR) build-api install-packages
	@echo -e "$(GREEN)✓ Development environment setup complete!$(NC)"
	@echo ""
	@echo "To activate the virtual environment:"
	@echo "  source $(VENV_DIR)/bin/activate"
	@echo ""
	@echo "Next steps:"
	@echo "  python ib.py services start  # Start services"
	@echo "  python ib.py test connection # Test connection"

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
	@echo -e "$(YELLOW)Installing CLI dependencies...$(NC)"
	$(VENV_PIP) install click

# Install just the development tools
dev-tools: $(VENV_DIR)
	@echo -e "$(YELLOW)Installing development tools...$(NC)"
	$(VENV_PIP) install ruff pytest pytest-cov click watchdog pydantic pydantic-settings
	@echo -e "$(GREEN)✓ Development tools installed$(NC)"

clean:
	@echo -e "$(YELLOW)Cleaning up...$(NC)"
	rm -rf $(VENV_DIR)
	rm -rf $(TWS_CLIENT_DIR)/build/
	rm -rf $(TWS_CLIENT_DIR)/dist/
	rm -rf $(TWS_CLIENT_DIR)/ibapi.egg-info/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo -e "$(GREEN)✓ Cleanup complete$(NC)"

# Legacy service management targets (deprecated)
# For all service operations, use: python ib.py
.PHONY: start-supervisor supervisor-status supervisor-logs supervisor-stop

start-supervisor: install-supervisor generate-instance-config
	@echo -e "$(YELLOW)Starting supervisor...$(NC)"
	@echo "DEPRECATED: Use 'python ib.py services start' instead"
	./start-supervisor.sh

supervisor-status:
	@echo -e "$(YELLOW)Supervisor status:$(NC)"
	@echo "DEPRECATED: Use 'python ib.py services status' instead"
	./supervisor-wrapper.sh status

supervisor-logs:
	@echo -e "$(YELLOW)Following logs...$(NC)"
	@echo "DEPRECATED: Use 'python ib.py services logs' instead"
	./supervisor-wrapper.sh tail -f ib-stream-remote

supervisor-stop:
	@echo -e "$(YELLOW)Stopping services...$(NC)"
	@echo "DEPRECATED: Use 'python ib.py services stop' instead"
	./supervisor-wrapper.sh stop all

# Helper targets for backward compatibility
install-supervisor: $(VENV_DIR)
	@echo -e "$(YELLOW)Installing supervisor...$(NC)"
	$(VENV_PIP) install supervisor

generate-instance-config:
	@echo -e "$(YELLOW)Generating instance configuration...$(NC)"
	$(VENV_PYTHON) generate_instance_config.py