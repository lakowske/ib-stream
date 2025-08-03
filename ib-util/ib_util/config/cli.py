"""
Configuration management CLI utility.

Provides commands to manage, validate, and migrate configurations
across multiple IB services.
"""

import sys
import json
from pathlib import Path
from typing import Optional

import click
from .base import IBEnvironment
from .loader import (
    load_config, 
    load_orchestration_for_environment,
    validate_configuration,
    ConfigLoader
)
from .orchestration import IBOrchestrationConfig


@click.group()
def config_cli():
    """IB Configuration Management CLI."""
    pass


@config_cli.command()
@click.option('--service', required=True, help='Service name (e.g., ib-stream, ib-contract)')
@click.option('--environment', type=click.Choice(['development', 'production', 'staging', 'testing']), 
              default='development', help='Target environment')
@click.option('--format', 'output_format', type=click.Choice(['json', 'yaml', 'env']), 
              default='json', help='Output format')
def show(service: str, environment: str, output_format: str):
    """Show configuration for a service."""
    try:
        env = IBEnvironment(environment)
        config = load_config(service, environment=env)
        
        if output_format == 'json':
            click.echo(json.dumps(config.dict(), indent=2, default=str))
        elif output_format == 'env':
            env_dict = config.to_env_dict()
            for key, value in env_dict.items():
                click.echo(f"{key}={value}")
        else:
            click.echo("YAML output not yet implemented")
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@config_cli.command()
@click.option('--environment', type=click.Choice(['development', 'production', 'staging', 'testing']), 
              default='development', help='Target environment')
@click.option('--output', help='Output file for supervisor configuration')
def orchestration(environment: str, output: Optional[str]):
    """Generate orchestration configuration."""
    try:
        env = IBEnvironment(environment)
        config = load_orchestration_for_environment(env)
        
        supervisor_config = config.to_supervisor_config()
        
        if output:
            Path(output).write_text(supervisor_config)
            click.echo(f"Supervisor configuration written to {output}")
        else:
            click.echo(supervisor_config)
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@config_cli.command()
def validate():
    """Validate configuration setup."""
    results = validate_configuration()
    
    if results['valid']:
        click.echo(click.style("✓ Configuration is valid", fg='green'))
    else:
        click.echo(click.style("✗ Configuration has errors", fg='red'))
    
    if results.get('errors'):
        click.echo("\nErrors:")
        for error in results['errors']:
            click.echo(click.style(f"  • {error}", fg='red'))
    
    if results.get('warnings'):
        click.echo("\nWarnings:")
        for warning in results['warnings']:
            click.echo(click.style(f"  • {warning}", fg='yellow'))
    
    if results.get('recommendations'):
        click.echo("\nRecommendations:")
        for rec in results['recommendations']:
            click.echo(click.style(f"  • {rec}", fg='blue'))
    
    if results.get('orchestration'):
        orch = results['orchestration']
        click.echo(f"\nOrchestration Info:")
        click.echo(f"  Services: {', '.join(orch['services'])}")
        click.echo(f"  Ports in use: {orch['ports_in_use']}")
        click.echo(f"  Client IDs in use: {orch['client_ids_in_use']}")
    
    if not results['valid']:
        sys.exit(1)


@config_cli.command()
@click.option('--environment', type=click.Choice(['development', 'production', 'staging', 'testing']), 
              required=True, help='Target environment')
@click.option('--output-dir', default='config', help='Output directory for new configuration files')
def migrate(environment: str, output_dir: str):
    """Migrate legacy configuration to new format."""
    try:
        env = IBEnvironment(environment)
        project_root = Path.cwd()
        output_path = project_root / output_dir
        output_path.mkdir(exist_ok=True)
        
        # Load current configuration
        loader = ConfigLoader(str(project_root))
        
        # Migrate legacy files
        legacy_files = [
            project_root / "ib-stream" / "config" / f"{environment}.env",
            project_root / "ib-stream" / "config" / "remote-gateway.env",
            project_root / "ib-stream" / "config" / "production-server.env",
        ]
        
        found_files = [f for f in legacy_files if f.exists()]
        
        if not found_files:
            click.echo("No legacy configuration files found to migrate")
            return
        
        click.echo(f"Found {len(found_files)} legacy files to migrate:")
        for f in found_files:
            click.echo(f"  • {f}")
        
        # Load and convert each legacy file
        for legacy_file in found_files:
            loader.load_legacy_env_file(str(legacy_file))
        
        # Create new configuration files
        base_config = loader.create_service_config("base", env)
        
        # Write new .env file
        new_env_file = output_path / f".env.{environment}"
        env_dict = base_config.to_env_dict()
        
        with open(new_env_file, 'w') as f:
            f.write(f"# Migrated configuration for {environment} environment\n")
            f.write(f"# Generated from legacy files: {[f.name for f in found_files]}\n\n")
            
            for key, value in env_dict.items():
                f.write(f"{key}={value}\n")
        
        click.echo(f"✓ Migrated configuration written to {new_env_file}")
        
        # Generate orchestration config
        orch_config = loader.create_orchestration_config(env)
        supervisor_file = project_root / f"supervisor-{environment}.conf"
        
        with open(supervisor_file, 'w') as f:
            f.write(orch_config.to_supervisor_config())
        
        click.echo(f"✓ Supervisor configuration written to {supervisor_file}")
        
        click.echo("\nMigration complete! Next steps:")
        click.echo("1. Review the generated configuration files")
        click.echo("2. Test with: ib-config validate")
        click.echo("3. Update your startup scripts to use the new configuration")
        
    except Exception as e:
        click.echo(f"Error during migration: {e}", err=True)
        sys.exit(1)


@config_cli.command()
@click.option('--environment', type=click.Choice(['development', 'production', 'staging', 'testing']), 
              default='development', help='Target environment')
@click.option('--service', help='Specific service to start (default: all enabled services)')
def start(environment: str, service: Optional[str]):
    """Start services using orchestration configuration."""
    try:
        env = IBEnvironment(environment)
        config = load_orchestration_for_environment(env)
        
        if service:
            # Start specific service
            service_config = config.get_service_config(service)
            if not service_config:
                click.echo(f"Service '{service}' not found or disabled", err=True)
                sys.exit(1)
            
            click.echo(f"Starting {service} in {environment} mode...")
            # TODO: Implement actual service startup
            click.echo(f"Service configuration: {service_config.dict()}")
        else:
            # Start all enabled services
            services = config.get_all_service_configs()
            if not services:
                click.echo("No enabled services found", err=True)
                sys.exit(1)
            
            click.echo(f"Starting {len(services)} services in {environment} mode...")
            for service_name, service_config in services.items():
                click.echo(f"  • {service_name}: port {service_config.server.port}")
            
            # TODO: Implement orchestrated startup
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    config_cli()