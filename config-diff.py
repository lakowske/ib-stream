#!/usr/bin/env python3
"""
Configuration comparison and diff tool.

Compare configurations between services, environments, or different versions.
Useful for debugging configuration issues and understanding changes.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# Add paths for modules
sys.path.insert(0, 'ib-util')
sys.path.insert(0, 'ib-stream/src')
sys.path.insert(0, 'ib-contract')

try:
    from ib_util.config.compat import create_compatible_config
    from ib_stream.config_v2 import create_config as create_stream_config
    import config_v2 as contract_config_v2
except ImportError as e:
    print(f"Error importing configuration modules: {e}")
    print("Make sure to run: make dev-tools")
    sys.exit(1)


def get_config_dict(service: str, config_type: str = "legacy") -> Dict[str, Any]:
    """Get configuration as a dictionary."""
    try:
        if config_type == "legacy":
            config = create_compatible_config(service)
            return config.to_dict() if hasattr(config, 'to_dict') else vars(config)
        elif config_type == "new":
            if service == "ib-stream":
                config = create_stream_config()
                return config.to_dict()
            elif service == "ib-contract":
                config = contract_config_v2.create_config()
                return config.to_dict()
            else:
                raise ValueError(f"New config not implemented for {service}")
        else:
            raise ValueError(f"Unknown config type: {config_type}")
    except Exception as e:
        return {"error": str(e)}


def format_value(value: Any, indent: int = 0) -> str:
    """Format a value for display with proper indentation."""
    prefix = "  " * indent
    
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for k, v in sorted(value.items()):
            lines.append(f"{prefix}  {k}: {format_value(v, indent + 1)}")
        lines.append(f"{prefix}}}")
        return "\n".join(lines)
    elif isinstance(value, list):
        if not value:
            return "[]"
        if len(value) == 1:
            return f"[{format_value(value[0], 0)}]"
        lines = ["["]
        for item in value:
            lines.append(f"{prefix}  {format_value(item, indent + 1)}")
        lines.append(f"{prefix}]")
        return "\n".join(lines)
    elif isinstance(value, str):
        return f'"{value}"'
    else:
        return str(value)


def show_config(service: str, config_type: str = "legacy"):
    """Show configuration for a service."""
    print(f"Configuration for {service} ({config_type}):")
    print("=" * 50)
    
    config_dict = get_config_dict(service, config_type)
    
    if "error" in config_dict:
        print(f"Error: {config_dict['error']}")
        return
    
    print(format_value(config_dict))


def compare_configs(service1: str, service2: str, config_type: str = "legacy"):
    """Compare configurations between two services."""
    print(f"Comparing {service1} vs {service2} ({config_type}):")
    print("=" * 60)
    
    config1 = get_config_dict(service1, config_type)
    config2 = get_config_dict(service2, config_type)
    
    if "error" in config1:
        print(f"Error loading {service1}: {config1['error']}")
        return
    
    if "error" in config2:
        print(f"Error loading {service2}: {config2['error']}")
        return
    
    # Find differences
    all_keys = sorted(set(config1.keys()) | set(config2.keys()))
    differences = []
    similarities = []
    
    for key in all_keys:
        if key not in config1:
            differences.append(f"  {key}: missing in {service1}, {format_value(config2[key])} in {service2}")
        elif key not in config2:
            differences.append(f"  {key}: {format_value(config1[key])} in {service1}, missing in {service2}")
        elif config1[key] != config2[key]:
            differences.append(f"  {key}:")
            differences.append(f"    {service1}: {format_value(config1[key])}")
            differences.append(f"    {service2}: {format_value(config2[key])}")
        else:
            similarities.append(f"  {key}: {format_value(config1[key])}")
    
    if differences:
        print("Differences:")
        for diff in differences:
            print(diff)
    else:
        print("No differences found!")
    
    if similarities and len(similarities) <= 10:  # Don't spam if too many similarities
        print(f"\nSimilarities ({len(similarities)} items):")
        for sim in similarities[:5]:  # Show first 5
            print(sim)
        if len(similarities) > 5:
            print(f"  ... and {len(similarities) - 5} more")


def compare_config_types(service: str):
    """Compare legacy vs new configuration for a service."""
    print(f"Comparing legacy vs new configuration for {service}:")
    print("=" * 60)
    
    legacy_config = get_config_dict(service, "legacy")
    
    try:
        new_config = get_config_dict(service, "new")
    except Exception as e:
        print(f"New configuration not available for {service}: {e}")
        return
    
    if "error" in legacy_config:
        print(f"Error loading legacy config: {legacy_config['error']}")
        return
    
    if "error" in new_config:
        print(f"Error loading new config: {new_config['error']}")
        return
    
    # Find common keys and differences
    common_keys = sorted(set(legacy_config.keys()) & set(new_config.keys()))
    legacy_only = sorted(set(legacy_config.keys()) - set(new_config.keys()))
    new_only = sorted(set(new_config.keys()) - set(legacy_config.keys()))
    
    print(f"Common keys: {len(common_keys)}")
    print(f"Legacy-only keys: {len(legacy_only)}")
    print(f"New-only keys: {len(new_only)}")
    print()
    
    # Show differences in common keys
    differences = []
    for key in common_keys:
        if legacy_config[key] != new_config[key]:
            differences.append(key)
    
    if differences:
        print(f"Different values in {len(differences)} common keys:")
        for key in differences[:5]:  # Show first 5
            print(f"  {key}:")
            print(f"    legacy: {format_value(legacy_config[key])}")
            print(f"    new: {format_value(new_config[key])}")
        if len(differences) > 5:
            print(f"  ... and {len(differences) - 5} more differences")
    else:
        print("All common keys have identical values!")
    
    if legacy_only:
        print(f"\nLegacy-only keys: {legacy_only}")
    
    if new_only:
        print(f"\nNew-only keys: {new_only}")


def main():
    parser = argparse.ArgumentParser(description="Compare and analyze configurations")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Show command
    show_parser = subparsers.add_parser("show", help="Show configuration for a service")
    show_parser.add_argument("service", choices=["ib-stream", "ib-contract", "ib-studies"])
    show_parser.add_argument("--type", choices=["legacy", "new"], default="legacy", help="Configuration type")
    
    # Compare services command
    compare_parser = subparsers.add_parser("compare", help="Compare configurations between services")
    compare_parser.add_argument("service1", choices=["ib-stream", "ib-contract", "ib-studies"])
    compare_parser.add_argument("service2", choices=["ib-stream", "ib-contract", "ib-studies"])
    compare_parser.add_argument("--type", choices=["legacy", "new"], default="legacy", help="Configuration type")
    
    # Compare config types command
    types_parser = subparsers.add_parser("types", help="Compare legacy vs new configuration for a service")
    types_parser.add_argument("service", choices=["ib-stream", "ib-contract"])
    
    # Summary command
    subparsers.add_parser("summary", help="Show configuration summary for all services")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "show":
            show_config(args.service, args.type)
        elif args.command == "compare":
            compare_configs(args.service1, args.service2, args.type)
        elif args.command == "types":
            compare_config_types(args.service)
        elif args.command == "summary":
            print("Configuration Summary:")
            print("=" * 50)
            for service in ["ib-stream", "ib-contract"]:
                try:
                    config = create_compatible_config(service)
                    if hasattr(config, 'host'):
                        print(f"{service:15} - Host: {config.host:15} Client ID: {config.client_id:3} Port: {config.server_port:4}")
                    else:
                        print(f"{service:15} - Configuration loaded successfully")
                except Exception as e:
                    print(f"{service:15} - Error: {e}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()