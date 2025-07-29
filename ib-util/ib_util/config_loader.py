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


def load_instance_env(instance_env_path: str = None) -> None:
    """Load instance-specific environment variables"""
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
    
    if not instance_env_path or not Path(instance_env_path).exists():
        return
        
    try:
        with open(instance_env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Only set if not already set
                    if key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Failed to load instance.env from {instance_env_path}: {e}")


def load_environment_config(service_type: str = "stream") -> ConnectionConfig:
    """
    Load connection configuration from environment variables
    
    Args:
        service_type: "stream" or "contracts" to determine which client ID to use
        
    Returns:
        ConnectionConfig with values from environment
    """
    # Load instance configuration first
    load_instance_env()
    
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