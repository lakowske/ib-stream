"""
IB Utilities - Shared utilities for Interactive Brokers API connections

This module provides common functionality for both ib-stream and ib-contracts services:
- Reliable connection handling with proper API handshake
- Environment configuration loading  
- Connection state management
- Error handling and logging
"""

from .connection import IBConnection, ConnectionConfig, create_connection, connect_with_retry
from .config_loader import load_environment_config

__all__ = ['IBConnection', 'ConnectionConfig', 'create_connection', 'connect_with_retry', 'load_environment_config']