"""
Configuration loading utilities for IB services
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ConnectionConfig:
    """Configuration for IB API connection"""
    host: str = "127.0.0.1"
    ports: List[int] = None
    client_id: int = 1
    connection_timeout: int = 15
    
    def __post_init__(self):
        if self.ports is None:
            self.ports = [7497, 7496, 4002, 4001]


def load_environment_file(env_file_path: str, override_existing: bool = False) -> None:
    """
    Load environment variables from a .env file with enhanced parsing features
    
    Features:
    - Variable substitution: ${VAR:-default} syntax
    - Quote removal for quoted values  
    - Comment and empty line handling
    
    Args:
        env_file_path: Path to the environment file
        override_existing: If True, override existing env vars; if False, only set unset vars
    """
    env_path = Path(env_file_path)
    if not env_path.exists():
        return  # No environment file found, use existing env vars
    
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Handle variable substitution ${VAR:-default}
                    if value.startswith('${') and ':-' in value and value.endswith('}'):
                        var_expr = value[2:-1]  # Remove ${ and }
                        var_name, default_value = var_expr.split(':-', 1)
                        value = os.getenv(var_name, default_value)
                    
                    # Set environment variable based on override setting
                    if override_existing or key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Failed to load environment file {env_path}: {e}")


def load_instance_env(instance_env_path: str = None) -> None:
    """Load instance-specific environment variables using enhanced parser"""
    if instance_env_path is None:
        # Try multiple possible locations
        possible_paths = [
            "ib-stream/config/instance.env",
            "../ib-stream/config/instance.env", 
            "../config/instance.env"
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                instance_env_path = path
                break
    
    if not instance_env_path:
        return
        
    # Use enhanced environment file parser, don't override existing vars
    load_environment_file(instance_env_path, override_existing=False)


def load_environment_file_with_detection(env_file_path: Optional[str] = None) -> None:
    """
    Load environment variables from a .env file with automatic detection
    
    Args:
        env_file_path: Optional specific path. If None, auto-detects based on IB_STREAM_ENV
    """
    if env_file_path is None:
        # Try to detect environment from IB_STREAM_ENV or default to production
        env_name = os.getenv("IB_STREAM_ENV", "production")
        env_file_path = f"config/{env_name}.env"
    
    env_path = Path(env_file_path)
    if not env_path.exists():
        # Try relative to current directory
        possible_paths = [
            env_file_path,
            f"../ib-stream/{env_file_path}",
            f"ib-stream/{env_file_path}",
            f"../{env_file_path}"
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                env_path = Path(path)
                break
    
    if env_path.exists():
        load_environment_file(str(env_path), override_existing=False)


def load_environment_config(service_type: str = "stream") -> ConnectionConfig:
    """
    Load connection configuration from environment variables with enhanced parsing
    
    Args:
        service_type: "stream" or "contracts" to determine which client ID to use
        
    Returns:
        ConnectionConfig with values from environment
    """
    # Load instance configuration first
    load_instance_env()
    
    # Load environment-specific configuration
    load_environment_file_with_detection()
    
    # Get connection settings
    host = os.getenv("IB_STREAM_HOST", "127.0.0.1")
    
    ports_env = os.getenv("IB_STREAM_PORTS", "7497,7496,4002,4001")
    try:
        ports = [int(p.strip()) for p in ports_env.split(",")]
    except ValueError:
        print(f"Warning: Invalid ports in IB_STREAM_PORTS: {ports_env}, using defaults")
        ports = [7497, 7496, 4002, 4001]
    
    # Determine client ID based on service type
    if service_type == "contracts":
        client_id = int(os.getenv("IB_CONTRACTS_CLIENT_ID", os.getenv("IB_STREAM_CLIENT_ID", "1")))
    else:
        client_id = int(os.getenv("IB_STREAM_CLIENT_ID", "1"))
    
    connection_timeout = int(os.getenv("IB_STREAM_CONNECTION_TIMEOUT", "15"))
    
    return ConnectionConfig(
        host=host,
        ports=ports,
        client_id=client_id,
        connection_timeout=connection_timeout
    )