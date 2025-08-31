#!/usr/bin/env python3
"""
Configuration v3 CLI Tools

Provides command-line utilities for managing the v3 configuration system.
"""

import click
import json
import yaml
from pathlib import Path
from .config_v3 import load_config, ConfigLoader


@click.group()
def config():
    """Configuration v3 management commands"""
    pass


@config.command()
@click.argument('service_name')
@click.option('--format', type=click.Choice(['yaml', 'json', 'summary']), default='summary')
@click.option('--config-root', help='Override config directory path')
def show(service_name, format, config_root):
    """Show configuration for a service"""
    try:
        config = load_config(service_name, config_root)
        
        if format == 'yaml':
            click.echo(yaml.dump(config.dict(), default_flow_style=False))
        elif format == 'json':
            click.echo(json.dumps(config.dict(), indent=2, default=str))
        else:  # summary
            click.echo(f"📋 Configuration Summary for {service_name}")
            click.echo(f"   Environment: {config.project.environment}")
            click.echo(f"   Server: {config.service.server.host}:{config.service.server.port}")
            click.echo(f"   Gateway: {config.gateway.host}:{config.gateway.ports}")
            click.echo(f"   Client ID: {config.service.client.id}")
            click.echo(f"   Storage: {config.storage.base_path} ({'enabled' if config.storage.enabled else 'disabled'})")
            click.echo(f"   Log Level: {config.logging.level}")
            if config.service.streaming:
                click.echo(f"   Background Streaming: {'enabled' if config.service.streaming.enable_background_streaming else 'disabled'}")
                
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise click.Abort()


@config.command()
@click.argument('service_name')
@click.option('--config-root', help='Override config directory path')
def validate(service_name, config_root):
    """Validate configuration for a service"""
    try:
        config = load_config(service_name, config_root)
        click.echo(f"✅ Configuration for {service_name} is valid")
        click.echo(f"   Environment: {config.project.environment}")
        click.echo(f"   All settings loaded successfully")
    except Exception as e:
        click.echo(f"❌ Configuration validation failed: {e}", err=True)
        raise click.Abort()


@config.command()
@click.option('--config-root', help='Override config directory path')
def validate_all(config_root):
    """Validate all service configurations"""
    services = ['ib-stream', 'ib-contract']
    results = {}
    
    for service in services:
        try:
            load_config(service, config_root)
            results[service] = True
            click.echo(f"✅ {service}: Valid")
        except Exception as e:
            results[service] = False
            click.echo(f"❌ {service}: {e}")
    
    if all(results.values()):
        click.echo(f"\n🎉 All configurations are valid!")
    else:
        failed = [s for s, valid in results.items() if not valid]
        click.echo(f"\n💥 Failed services: {', '.join(failed)}")
        raise click.Abort()


@config.command()
@click.option('--config-root', help='Override config directory path', default='config')
def info(config_root):
    """Show information about the configuration system"""
    config_path = Path(config_root)
    
    click.echo(f"📁 Configuration System v3 Info")
    click.echo(f"   Config Root: {config_path.absolute()}")
    click.echo(f"   Exists: {'✅' if config_path.exists() else '❌'}")
    
    if config_path.exists():
        files = list(config_path.rglob('*.yaml'))
        click.echo(f"   YAML Files: {len(files)}")
        for file in sorted(files):
            rel_path = file.relative_to(config_path)
            click.echo(f"     - {rel_path}")
    
    click.echo(f"\n🌍 Environment: {ConfigLoader().get_environment()}")


if __name__ == '__main__':
    config()