#!/usr/bin/env python3
"""
Smart Instance Configuration Generator

Generates unique client IDs and ports based on project path to avoid collisions
between multiple git worktrees, clones, and development instances.
"""

import hashlib
import os
import sys
from pathlib import Path


def hash_path_to_number(path: str, base: int, range_size: int) -> int:
    """
    Convert a file path to a consistent number within a range.
    
    Args:
        path: The file path to hash
        base: Base number to start from
        range_size: Size of the range to map into
        
    Returns:
        A number between base and base + range_size - 1
    """
    # Create hash of the absolute path
    abs_path = os.path.abspath(path)
    path_hash = hashlib.md5(abs_path.encode()).hexdigest()
    
    # Convert hash to integer and map to range
    hash_int = int(path_hash[:8], 16)  # Use first 8 hex chars
    return base + (hash_int % range_size)


def generate_instance_config(project_root: str = None) -> dict:
    """
    Generate unique configuration for this project instance.
    
    Args:
        project_root: Path to project root (defaults to current directory)
        
    Returns:
        Dictionary with generated configuration
    """
    if project_root is None:
        project_root = os.getcwd()
    
    project_root = os.path.abspath(project_root)
    
    # Generate unique base ID from project path
    # Use range 100-999 for client IDs (allows ~900 concurrent instances)
    base_client_id = hash_path_to_number(project_root, 100, 900)
    
    # Generate unique base port from project path  
    # Use range 8000-8999 for HTTP ports (allows ~1000 concurrent instances)
    base_port = hash_path_to_number(project_root, 8000, 1000)
    
    # Ensure ib-stream and ib-contracts get different client IDs
    stream_client_id = base_client_id
    contracts_client_id = base_client_id + 1
    
    # Ensure ib-stream and ib-contracts get different ports
    stream_port = base_port
    contracts_port = base_port + 10  # Skip 10 to avoid common conflicts
    
    config = {
        'project_root': project_root,
        'base_hash': hashlib.md5(project_root.encode()).hexdigest()[:8],
        
        # Client IDs
        'stream_client_id': stream_client_id,
        'contracts_client_id': contracts_client_id,
        
        # HTTP Ports  
        'stream_port': stream_port,
        'contracts_port': contracts_port,
        
        # Environment variables format
        'env_vars': {
            'IB_STREAM_CLIENT_ID': str(stream_client_id),
            'IB_CONTRACTS_CLIENT_ID': str(contracts_client_id),
            'IB_STREAM_PORT': str(stream_port),
            'IB_CONTRACTS_PORT': str(contracts_port),
        }
    }
    
    return config


def write_env_file(config: dict, env_file: str = None) -> None:
    """Write configuration to environment file."""
    if env_file is None:
        env_file = "ib-stream/config/instance.env"
        
    env_path = Path(env_file)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(env_path, 'w') as f:
        f.write(f"# Auto-generated instance configuration\n")
        f.write(f"# Project: {config['project_root']}\n")
        f.write(f"# Hash: {config['base_hash']}\n")
        f.write(f"#\n")
        f.write(f"# This file is generated automatically to avoid collisions between\n")
        f.write(f"# multiple git worktrees, clones, and development instances.\n")
        f.write(f"#\n")
        f.write(f"# Stream Service (port {config['stream_port']})\n")
        f.write(f"IB_STREAM_CLIENT_ID={config['stream_client_id']}\n")
        f.write(f"IB_STREAM_PORT={config['stream_port']}\n")
        f.write(f"#\n")
        f.write(f"# Contracts Service (port {config['contracts_port']})\n") 
        f.write(f"IB_CONTRACTS_CLIENT_ID={config['contracts_client_id']}\n")
        f.write(f"IB_CONTRACTS_PORT={config['contracts_port']}\n")


def main():
    """CLI interface for generating instance configuration."""
    project_root = sys.argv[1] if len(sys.argv) > 1 else None
    
    config = generate_instance_config(project_root)
    
    print("Generated Instance Configuration:")
    print(f"  Project: {config['project_root']}")
    print(f"  Hash: {config['base_hash']}")
    print()
    print(f"  Stream Service:")
    print(f"    Client ID: {config['stream_client_id']}")  
    print(f"    HTTP Port: {config['stream_port']}")
    print()
    print(f"  Contracts Service:")
    print(f"    Client ID: {config['contracts_client_id']}")
    print(f"    HTTP Port: {config['contracts_port']}")
    print()
    
    # Write to environment file
    write_env_file(config)
    print(f"✓ Configuration written to ib-stream/config/instance.env")


if __name__ == "__main__":
    main()