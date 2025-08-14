#!/usr/bin/env python3
"""
IB-Stream Management CLI

A modular command-line interface for managing IB-Stream services, configuration,
and development workflows. Replaces complex Makefile targets with proper
command/subcommand structure.

Usage:
    ./ib-cli.py config validate
    ./ib-cli.py config show --service ib-stream
    ./ib-cli.py config watch --service ib-stream
    ./ib-cli.py services start --environment production
    ./ib-cli.py services status
"""

import sys
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import click
from click import echo, style

# Add paths for imports
sys.path.insert(0, 'ib-util')
sys.path.insert(0, 'ib-stream/src')
sys.path.insert(0, 'ib-contract')

# Project paths
PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT / '.venv' / 'bin' / 'python'


def run_command(cmd: List[str], description: str = None, check: bool = True, cwd: Path = None) -> subprocess.CompletedProcess:
    """Run a command with proper error handling."""
    if description:
        echo(style(f"→ {description}...", fg='yellow'))
    
    working_dir = cwd or PROJECT_ROOT
    
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True, cwd=working_dir)
        if result.stdout:
            echo(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        echo(style(f"Error: {e}", fg='red'))
        if e.stderr:
            echo(style(e.stderr, fg='red'))
        if check:
            sys.exit(1)
        return e


def ensure_venv():
    """Ensure virtual environment and dependencies are available."""
    if not VENV_PYTHON.exists():
        echo(style("Virtual environment not found. Run 'make setup' first.", fg='red'))
        sys.exit(1)


@click.group()
@click.version_option(version="2.0.0", prog_name="ib-cli")
def cli():
    """IB-Stream Management CLI - Configuration, Services, and Development Tools"""
    pass


# =============================================================================
# Configuration Management Commands
# =============================================================================

@cli.group()
def config():
    """Configuration management commands"""
    pass


@config.command()
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def validate(verbose):
    """Validate configuration system health"""
    ensure_venv()
    
    echo(style("Validating configuration system...", fg='yellow'))
    
    try:
        from ib_util.config.compat import validate_v2_config
        result = validate_v2_config()
        
        if result['valid']:
            echo(style("✓ Configuration system is healthy", fg='green'))
        else:
            echo(style("✗ Configuration system has issues", fg='red'))
        
        if verbose or not result['valid']:
            echo("\nDetailed Results:")
            echo(json.dumps(result, indent=2))
        
        if result.get('recommendations'):
            echo(style("\nRecommendations:", fg='blue'))
            for rec in result['recommendations']:
                echo(f"  • {rec}")
        
        sys.exit(0 if result['valid'] else 1)
        
    except Exception as e:
        echo(style(f"Configuration validation failed: {e}", fg='red'))
        sys.exit(1)


@config.command()
@click.option('--service', type=click.Choice(['ib-stream', 'ib-contract', 'all']), 
              default='all', help='Service to show configuration for')
@click.option('--format', 'output_format', type=click.Choice(['summary', 'detailed', 'json']), 
              default='summary', help='Output format')
def show(service, output_format):
    """Show current configuration"""
    ensure_venv()
    
    services = ['ib-stream', 'ib-contract'] if service == 'all' else [service]
    
    for svc in services:
        echo(style(f"\n{svc} Configuration:", fg='cyan', bold=True))
        echo("=" * 50)
        
        try:
            from ib_util.config.compat import create_compatible_config
            config = create_compatible_config(svc)
            
            if output_format == 'json':
                if hasattr(config, 'to_dict'):
                    echo(json.dumps(config.to_dict(), indent=2, default=str))
                else:
                    echo(json.dumps(vars(config), indent=2, default=str))
            elif output_format == 'detailed':
                if hasattr(config, 'to_dict'):
                    config_dict = config.to_dict()
                    for key, value in config_dict.items():
                        echo(f"  {key}: {value}")
                else:
                    for key, value in vars(config).items():
                        echo(f"  {key}: {value}")
            else:  # summary
                # Access nested v2 configuration structure
                connection = getattr(config, 'connection', None)
                server = getattr(config, 'server', None)
                storage = getattr(config, 'storage', None)
                
                host = getattr(connection, 'host', 'N/A') if connection else 'N/A'
                client_id = getattr(connection, 'client_id', 'N/A') if connection else 'N/A'
                server_port = getattr(server, 'port', 'N/A') if server else 'N/A'
                storage_enabled = getattr(storage, 'enable_storage', 'N/A') if storage else 'N/A'
                
                echo(f"  Host: {host}")
                echo(f"  Client ID: {client_id}")
                echo(f"  Server Port: {server_port}")
                echo(f"  Storage: {storage_enabled}")
                
        except Exception as e:
            echo(style(f"  Error loading configuration: {e}", fg='red'))


@config.command()
@click.option('--service', type=click.Choice(['ib-stream', 'ib-contract', 'all']), 
              default='all', help='Service to watch')
def watch(service):
    """Watch configuration files for changes (hot-reload)"""
    click.echo("Configuration hot-reload:")
    click.echo("=======================")
    click.echo("Legacy config-watch.py has been removed with the old configuration system")
    click.echo("The new configuration system uses:")
    click.echo("- ib-stream: config_v2.py with automatic environment detection")
    click.echo("- ib-contract: ib-util config with hot-reload built-in")
    click.echo("")
    click.echo("For development:")
    click.echo("1. Edit environment variables in supervisor.conf")
    click.echo("2. Restart services: python ib.py services restart")
    click.echo("3. Check configuration: python ib.py config show")


@config.command()
@click.argument('service1', type=click.Choice(['ib-stream', 'ib-contract']))
@click.argument('service2', type=click.Choice(['ib-stream', 'ib-contract']))
def compare(service1, service2):
    """Compare configurations between services"""
    click.echo(f"Comparing {service1} vs {service2} configurations:")
    click.echo("Note: Using new configuration system - legacy config-diff.py removed")
    
    # Simple comparison using new config system
    try:
        import os
        os.environ['IB_ENVIRONMENT'] = 'development'
        
        click.echo(f"\n{service1} configuration:")
        if service1 == 'ib-stream':
            os.environ['IB_SERVICE_NAME'] = 'ib-stream'
            from ib_stream.config_v2 import create_config
            config1 = create_config()
            click.echo(f"  Host: {config1.host}")
            click.echo(f"  Client ID: {config1.client_id}")
            click.echo(f"  Server Port: {config1.server_port}")
        else:
            click.echo("  ib-contract uses ib-util config system")
        
        click.echo(f"\n{service2} configuration:")
        if service2 == 'ib-stream':
            os.environ['IB_SERVICE_NAME'] = 'ib-stream'
            from ib_stream.config_v2 import create_config
            config2 = create_config()
            click.echo(f"  Host: {config2.host}")
            click.echo(f"  Client ID: {config2.client_id}")
            click.echo(f"  Server Port: {config2.server_port}")
        else:
            click.echo("  ib-contract uses ib-util config system")
            
    except Exception as e:
        click.echo(f"Error comparing configurations: {e}")


@config.command()
def summary():
    """Show configuration summary for all services"""
    click.echo("Configuration Summary:")
    click.echo("====================")
    click.echo("All services now use the new unified configuration system")
    click.echo("- ib-stream: config_v2.py with type-safe validation")
    click.echo("- ib-contract: ib-util configuration system")
    click.echo("- Legacy config.py and related files have been removed")


# =============================================================================
# Service Management Commands  
# =============================================================================

@cli.group()
def services():
    """Service management and orchestration"""
    pass


def ensure_supervisor_config():
    """Ensure supervisor configuration and instance config are ready"""
    echo(style("Generating instance configuration...", fg='yellow'))
    run_command([str(VENV_PYTHON), 'generate_instance_config.py'])


def load_instance_config():
    """Load instance configuration from ib-stream/config/instance.env"""
    instance_config = {}
    instance_file = PROJECT_ROOT / 'ib-stream' / 'config' / 'instance.env'
    
    if instance_file.exists():
        try:
            with open(instance_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        instance_config[key] = value
        except Exception as e:
            echo(style(f"Warning: Could not load instance config: {e}", fg='yellow'))
    
    return instance_config


def get_supervisorctl():
    """Get the supervisorctl path with unified configuration"""
    # Generate a concrete supervisor configuration without environment variables
    generate_concrete_supervisor_config()
    
    # Always use the concrete supervisor.conf
    return ([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisorctl'), '-c', 'supervisor.conf'], os.environ.copy())


def generate_concrete_supervisor_config():
    """Generate a concrete supervisor configuration with resolved paths"""
    # Load instance configuration for port and client ID assignments
    instance_config = load_instance_config()
    
    # Template for supervisor configuration
    config_template = f"""[unix_http_server]
file={PROJECT_ROOT}/supervisor.sock

[supervisord]
logfile={PROJECT_ROOT}/logs/supervisord.log
pidfile={PROJECT_ROOT}/supervisord.pid
childlogdir={PROJECT_ROOT}/logs
nodaemon=false

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://{PROJECT_ROOT}/supervisor.sock

# Development Services (autostart=false, start only when needed)
[program:ib-stream-development]
command={PROJECT_ROOT}/.venv/bin/uvicorn ib_stream.api_server:app --host 0.0.0.0 --port {instance_config.get('IB_STREAM_PORT', '8774')} --reload
directory={PROJECT_ROOT}/ib-stream
environment=IB_ENVIRONMENT="development",IB_SERVICE_NAME="ib-stream",PROJECT_ROOT="{PROJECT_ROOT}",IB_STREAM_HOST="192.168.0.60",IB_STREAM_PORTS="4002,4001",IB_STREAM_CLIENT_ID="{instance_config.get('IB_STREAM_CLIENT_ID', '374')}",IB_CONNECTION_TIMEOUT="10",IB_RECONNECT_ATTEMPTS="5",IB_STREAM_ENABLE_STORAGE="true",IB_STREAM_STORAGE_PATH="storage-dev",IB_STREAM_ENABLE_JSON="true",IB_STREAM_ENABLE_PROTOBUF="false",IB_STREAM_ENABLE_POSTGRES="false",IB_STREAM_ENABLE_METRICS="true",IB_STREAM_ENABLE_BACKGROUND_STREAMING="false",IB_STREAM_TRACKED_CONTRACTS="",IB_STREAM_BUFFER_SIZE="100",IB_STREAM_BIND_HOST="0.0.0.0",IB_STREAM_PORT="{instance_config.get('IB_STREAM_PORT', '8774')}",IB_STREAM_LOG_LEVEL="DEBUG",IB_STREAM_MAX_STREAMS="10"
autostart=false
autorestart=true
startretries=3
user={os.getenv('USER', 'unknown')}
stdout_logfile={PROJECT_ROOT}/logs/ib-stream-development-stdout.log
stderr_logfile={PROJECT_ROOT}/logs/ib-stream-development-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5

[program:ib-contract-development]
command={PROJECT_ROOT}/.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port {instance_config.get('IB_CONTRACTS_PORT', '8784')} --reload
directory={PROJECT_ROOT}/ib-contract
environment=IB_ENVIRONMENT="development",IB_SERVICE_NAME="ib-contract",PROJECT_ROOT="{PROJECT_ROOT}",IB_STREAM_HOST="192.168.0.60",IB_STREAM_PORTS="4002,4001",IB_STREAM_CLIENT_ID="{instance_config.get('IB_CONTRACTS_CLIENT_ID', '375')}",IB_CONNECTION_TIMEOUT="10",IB_RECONNECT_ATTEMPTS="5",IB_STREAM_ENABLE_STORAGE="true",IB_STREAM_STORAGE_PATH="storage-dev",IB_STREAM_ENABLE_JSON="true",IB_STREAM_ENABLE_PROTOBUF="false",IB_STREAM_ENABLE_POSTGRES="false",IB_STREAM_ENABLE_METRICS="true",IB_STREAM_ENABLE_BACKGROUND_STREAMING="false",IB_STREAM_TRACKED_CONTRACTS="",IB_CONTRACTS_PORT="{instance_config.get('IB_CONTRACTS_PORT', '8784')}"
autostart=false
autorestart=true
startretries=3
user={os.getenv('USER', 'unknown')}
stdout_logfile={PROJECT_ROOT}/logs/ib-contract-development-stdout.log
stderr_logfile={PROJECT_ROOT}/logs/ib-contract-development-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5

# Production Services (autostart=false, start only when needed)
[program:ib-stream-production]
command={PROJECT_ROOT}/.venv/bin/uvicorn ib_stream.api_server:app --host 0.0.0.0 --port 8851
directory={PROJECT_ROOT}/ib-stream
environment=IB_ENVIRONMENT="production",IB_SERVICE_NAME="ib-stream",PROJECT_ROOT="{PROJECT_ROOT}",IB_STREAM_HOST="localhost",IB_STREAM_PORTS="4002",IB_STREAM_CLIENT_ID="851",IB_CONNECTION_TIMEOUT="10",IB_RECONNECT_ATTEMPTS="5",IB_STREAM_ENABLE_STORAGE="true",IB_STREAM_STORAGE_PATH="storage",IB_STREAM_ENABLE_JSON="true",IB_STREAM_ENABLE_PROTOBUF="true",IB_STREAM_ENABLE_POSTGRES="true",IB_STREAM_ENABLE_METRICS="true",IB_STREAM_ENABLE_BACKGROUND_STREAMING="true",IB_STREAM_TRACKED_CONTRACTS="711280073:MNQ:bid_ask;last:24",IB_STREAM_BUFFER_SIZE="1000",IB_STREAM_BIND_HOST="0.0.0.0",IB_STREAM_PORT="8851",IB_STREAM_LOG_LEVEL="INFO",IB_STREAM_MAX_STREAMS="100"
autostart=false
autorestart=true
startretries=3
user={os.getenv('USER', 'unknown')}
stdout_logfile={PROJECT_ROOT}/logs/ib-stream-production-stdout.log
stderr_logfile={PROJECT_ROOT}/logs/ib-stream-production-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5

[program:ib-contract-production]
command={PROJECT_ROOT}/.venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8861
directory={PROJECT_ROOT}/ib-contract
environment=IB_ENVIRONMENT="production",IB_SERVICE_NAME="ib-contract",PROJECT_ROOT="{PROJECT_ROOT}",IB_STREAM_HOST="localhost",IB_STREAM_PORTS="4002",IB_STREAM_CLIENT_ID="852",IB_CONNECTION_TIMEOUT="10",IB_RECONNECT_ATTEMPTS="5",IB_STREAM_ENABLE_STORAGE="true",IB_STREAM_STORAGE_PATH="storage",IB_STREAM_ENABLE_JSON="true",IB_STREAM_ENABLE_PROTOBUF="true",IB_STREAM_ENABLE_POSTGRES="true",IB_STREAM_ENABLE_METRICS="true",IB_STREAM_ENABLE_BACKGROUND_STREAMING="true",IB_STREAM_TRACKED_CONTRACTS="711280073:MNQ:bid_ask;last:24",IB_CONTRACTS_PORT="8861"
autostart=false
autorestart=true
startretries=3
user={os.getenv('USER', 'unknown')}
stdout_logfile={PROJECT_ROOT}/logs/ib-contract-production-stdout.log
stderr_logfile={PROJECT_ROOT}/logs/ib-contract-production-stderr.log
stdout_logfile_maxbytes=10MB
stderr_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile_backups=5
"""
    
    # Write the concrete configuration
    supervisor_config_path = PROJECT_ROOT / 'supervisor.conf'
    with open(supervisor_config_path, 'w') as f:
        f.write(config_template)


def show_resolved_config(env, environment):
    """Show the supervisor configuration with all variables resolved"""
    import re
    
    echo(style(f"🔍 Resolved supervisor.conf for {environment} environment:", fg='cyan', bold=True))
    echo()
    
    # Show environment variables that will be used
    echo(style("Environment Variables:", fg='yellow', bold=True))
    relevant_vars = {k: v for k, v in env.items() if k.startswith('ENV_')}
    for key, value in sorted(relevant_vars.items()):
        echo(style(f"  {key}", fg='green') + f" = {value}")
    echo()
    
    # Read and resolve the supervisor config
    supervisor_config_path = PROJECT_ROOT / 'supervisor.conf'
    if not supervisor_config_path.exists():
        echo(style("❌ supervisor.conf not found!", fg='red'))
        return
    
    try:
        with open(supervisor_config_path, 'r') as f:
            config_content = f.read()
        
        # Perform environment variable substitution
        def substitute_var(match):
            var_name = match.group(1)
            if var_name in env:
                return env[var_name]
            else:
                return f"<UNRESOLVED:{var_name}>"
        
        # Replace %(VAR_NAME)s patterns with environment variable values
        resolved_content = re.sub(r'%\(([^)]+)\)s', substitute_var, config_content)
        
        echo(style("Resolved Configuration:", fg='yellow', bold=True))
        echo(style("─" * 60, fg='blue'))
        echo(resolved_content)
        echo(style("─" * 60, fg='blue'))
        
        # Check for unresolved variables
        unresolved = re.findall(r'<UNRESOLVED:([^>]+)>', resolved_content)
        if unresolved:
            echo()
            echo(style("⚠️  Unresolved variables found:", fg='red', bold=True))
            for var in set(unresolved):
                echo(style(f"  - {var}", fg='red'))
        else:
            echo()
            echo(style("✅ All variables resolved successfully!", fg='green', bold=True))
            
    except Exception as e:
        echo(style(f"❌ Error reading supervisor config: {e}", fg='red'))


@services.command()
@click.option('--environment', type=click.Choice(['development', 'production']), 
              default='production', help='Target environment')
@click.option('--dry-run', is_flag=True, help='Show resolved configuration without starting services')
def start(environment, dry_run):
    """Start services with supervisor"""
    ensure_venv()
    ensure_supervisor_config()
    
    # Set environment variables (reuse the same logic as get_supervisorctl)
    _, env = get_supervisorctl()
    
    if dry_run:
        show_resolved_config(env, environment)
        return
    
    echo(style(f"Starting services in {environment} mode...", fg='yellow'))
    
    socket_file = PROJECT_ROOT / 'supervisor.sock'
    
    # Clean up stale socket file if supervisor isn't actually running
    import subprocess
    if socket_file.exists():
        try:
            test_result = subprocess.run([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisorctl'), '-c', 'supervisor.conf', 'status'], 
                                       capture_output=True, text=True, env=env, timeout=3)
            if 'no such file' in test_result.stderr.lower() or test_result.returncode != 0:
                echo(style("Cleaning up stale supervisor socket...", fg='yellow'))
                socket_file.unlink()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            echo(style("Cleaning up stale supervisor socket...", fg='yellow'))
            socket_file.unlink()
    
    # Start supervisord if not running
    echo(style("Starting supervisor daemon...", fg='yellow'))
    try:
        result = subprocess.run([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisord'), '-c', 'supervisor.conf'], 
                               capture_output=True, text=True, env=env, timeout=10)
        if result.returncode == 0:
            echo(style("✓ Supervisor daemon started successfully", fg='green'))
        elif "already listening" in result.stderr or "already exists" in result.stderr:
            echo(style("✓ Supervisor daemon already running", fg='green'))
        else:
            echo(style(f"✗ Supervisor daemon failed to start:", fg='red'))
            echo(style(result.stderr.strip(), fg='red'))
            sys.exit(1)
    except subprocess.TimeoutExpired:
        echo(style("✗ Supervisor daemon startup timeout", fg='red'))
        sys.exit(1)
    except Exception as e:
        echo(style(f"✗ Failed to start supervisor daemon: {e}", fg='red'))
        sys.exit(1)
    
    # Stop services from other environment first
    echo(style("Stopping services from other environments...", fg='yellow'))
    cmd, env = get_supervisorctl()
    other_env = 'production' if environment == 'development' else 'development'
    other_services = [f'ib-stream-{other_env}', f'ib-contract-{other_env}']
    for service in other_services:
        result = subprocess.run(cmd + ['stop', service], capture_output=True, text=True, env=env)
        # Ignore errors for services that aren't running
    
    # Start services for the requested environment
    echo(style(f"Starting {environment} services...", fg='green'))
    target_services = [f'ib-stream-{environment}', f'ib-contract-{environment}']
    
    for service in target_services:
        result = subprocess.run(cmd + ['start', service], capture_output=True, text=True, env=env)
        if result.stdout:
            echo(result.stdout)
        if result.stderr:
            echo(style(result.stderr, fg='yellow'))


@services.command()
def status():
    """Show service status"""
    ensure_venv()
    echo(style("Service Status:", fg='cyan'))
    cmd, env = get_supervisorctl()
    
    import subprocess
    result = subprocess.run(cmd + ['status'], capture_output=True, text=True, env=env)
    if result.stdout:
        echo(result.stdout)
    if result.stderr and result.returncode != 0:
        echo(style(result.stderr, fg='red'))


@services.command()
def stop():
    """Stop all services"""
    ensure_venv()
    echo(style("Stopping services...", fg='yellow'))
    cmd, env = get_supervisorctl()
    
    import subprocess
    result = subprocess.run(cmd + ['stop', 'all'], capture_output=True, text=True, env=env)
    if result.stdout:
        echo(result.stdout)
    if result.stderr:
        echo(style(result.stderr, fg='yellow'))


@services.command()
@click.argument('service', required=False)
def restart(service):
    """Restart services (or specific service)"""
    ensure_venv()
    cmd, env = get_supervisorctl()
    
    import subprocess
    if service:
        echo(style(f"Restarting {service}...", fg='yellow'))
        result = subprocess.run(cmd + ['restart', service], capture_output=True, text=True, env=env)
    else:
        echo(style("Restarting all services...", fg='yellow'))
        result = subprocess.run(cmd + ['restart', 'all'], capture_output=True, text=True, env=env)
    
    if result.stdout:
        echo(result.stdout)
    if result.stderr:
        echo(style(result.stderr, fg='yellow'))


@services.command()
@click.option('--service', help='Show logs for specific service')
@click.option('--follow', '-f', is_flag=True, help='Follow logs in real time')
def logs(service, follow):
    """Show service logs"""
    ensure_venv()
    cmd, env = get_supervisorctl()
    
    import subprocess
    if service:
        if follow:
            echo(style(f"Following logs for {service} (Ctrl+C to stop)...", fg='yellow'))
            # For follow mode, don't capture output - let it stream
            subprocess.run(cmd + ['tail', '-f', service], env=env)
        else:
            echo(style(f"Recent logs for {service}:", fg='cyan'))
            result = subprocess.run(cmd + ['tail', service], capture_output=True, text=True, env=env)
            if result.stdout:
                echo(result.stdout)
            if result.stderr:
                echo(style(result.stderr, fg='red'))
    else:
        echo(style("Available services:", fg='cyan'))
        result = subprocess.run(cmd + ['status'], capture_output=True, text=True, env=env)
        if result.stdout:
            echo(result.stdout)
        echo(style("\nUse --service <name> to view specific logs", fg='yellow'))




# =============================================================================
# Testing Commands
# =============================================================================

@cli.group()
def test():
    """Testing and validation commands"""
    pass


@test.command()
def connection():
    """Test connection to IB Gateway"""
    ensure_venv()
    echo(style("Testing connection with new configuration system...", fg='yellow'))
    
    run_command([
        str(VENV_PYTHON), '-c',
        """
import sys; sys.path.insert(0, 'ib-stream/src')
from ib_stream.app_lifecycle import get_app_state
app_state = get_app_state()
config = app_state['config']
print(f'Host: {config.host}')
print(f'Ports: {config.ports}')
print(f'Client ID: {config.client_id}')
print(f'Storage: {config.storage.enable_storage}')
        """
    ])
    
    echo(style("Testing with sample contract using localhost:4002...", fg='yellow'))
    # Use direct connection test to localhost:4002 with unique client ID
    env = os.environ.copy()
    env['IB_STREAM_HOST'] = 'localhost'
    env['IB_STREAM_PORTS'] = '4002'
    env['IB_STREAM_CLIENT_ID'] = '777'  # Use unique client ID for testing
    env['IB_ENVIRONMENT'] = 'test'
    
    # Simple connection test using StreamingApp directly
    cmd = [str(VENV_PYTHON), '-c', """
import sys; sys.path.insert(0, 'ib-stream/src')
import os, time
from ib_stream.streaming_app import StreamingApp
from ib_stream.config_v2 import create_config

# Set test environment variables for config
os.environ['IB_STREAM_HOST'] = 'localhost'
os.environ['IB_STREAM_PORTS'] = '4002'
os.environ['IB_STREAM_CLIENT_ID'] = '777'
os.environ['IB_ENVIRONMENT'] = 'development'
os.environ['IB_STREAM_ENABLE_STORAGE'] = 'false'

# Create test config with environment overrides
test_config = create_config()

app = StreamingApp(test_config)
app.connect_and_start()
time.sleep(2)  # Give time to connect
if app.is_connected():
    print('✓ Connected successfully to IB Gateway')
else:
    print('✗ Failed to connect to IB Gateway')
app.disconnect_and_stop()
"""]
    
    import subprocess
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT / 'ib-stream', env=env, timeout=10)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(cmd, 124, stdout='', stderr='Connection timeout')
    
    if result.returncode == 0:
        echo(style("✓ Connection test successful", fg='green'))
        if result.stdout.strip():
            echo(result.stdout.strip())
    else:
        echo(style("✗ Connection test failed - check IB Gateway", fg='red'))
        if result.stderr.strip():
            echo(style(f"Error: {result.stderr.strip()}", fg='red'))
        echo(style(f"Return code: {result.returncode}", fg='yellow'))


@test.command()
@click.argument('symbol', default='AAPL')
def contract(symbol):
    """Test contract lookup"""
    ensure_venv()
    echo(style(f"Testing contract lookup for {symbol}...", fg='yellow'))
    
    run_command([str(VENV_PYTHON), 'ib-contract/contract_lookup.py', symbol])


# =============================================================================
# Development Commands
# =============================================================================

@cli.group()
def dev():
    """Development and maintenance commands"""
    pass


@cli.group()
def monitor():
    """Monitoring and health check commands"""
    pass


@dev.command()
def setup():
    """Set up development environment"""
    echo(style("Setting up development environment...", fg='yellow'))
    run_command(['make', 'setup'])


@dev.command()
def clean():
    """Clean build artifacts and temporary files"""
    echo(style("Cleaning up...", fg='yellow'))
    run_command(['make', 'clean'])


@dev.command()
def tools():
    """Install development tools"""
    echo(style("Installing development tools...", fg='yellow'))
    run_command(['make', 'dev-tools'])


# =============================================================================
# Main Entry Point
# =============================================================================

# =============================================================================
# Monitoring Commands
# =============================================================================

@monitor.command('status')
def monitor_status():
    """Show overall system health status"""
    try:
        import requests
        
        # Check both service health endpoints
        services = [
            ('ib-stream', 'http://localhost:8851/health'),
            ('ib-contract', 'http://localhost:8861/health')
        ]
        
        echo(style("System Health Status", fg='cyan', bold=True))
        echo("=" * 50)
        
        overall_healthy = True
        
        for service_name, url in services:
            try:
                response = requests.get(url, timeout=5)
                data = response.json()
                
                status = data.get('status', 'unknown')
                tws_connected = data.get('tws_connected', False)
                time_sync = data.get('time_sync', {})
                
                # Format status with color
                if status == 'healthy':
                    status_color = 'green'
                elif status == 'warning' or status == 'degraded':
                    status_color = 'yellow'
                    overall_healthy = False
                else:
                    status_color = 'red'
                    overall_healthy = False
                
                echo(f"{service_name:15} | {style(status.upper(), fg=status_color, bold=True)}")
                echo(f"{'':15} | TWS: {'✓' if tws_connected else '✗'}")
                
                if time_sync:
                    drift = time_sync.get('drift_ms', 0)
                    echo(f"{'':15} | Time: {drift:+.1f}ms ({time_sync.get('classification', 'unknown')})")
                
            except Exception as e:
                echo(f"{service_name:15} | {style('ERROR', fg='red', bold=True)} - {str(e)}")
                overall_healthy = False
        
        echo("=" * 50)
        if overall_healthy:
            echo(style("✓ All systems operational", fg='green', bold=True))
        else:
            echo(style("⚠ Issues detected - check service logs", fg='yellow', bold=True))
            
    except ImportError:
        echo(style("Error: requests library not installed", fg='red'))
        echo("Install with: pip install requests")

@monitor.command('ntp-time-drift')
@click.option('--samples', '-s', default=5, help='Number of samples per server')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
def monitor_ntp_time_drift(samples: int, output_json: bool):
    """Check time drift using direct NTP server queries (legacy method)"""
    try:
        from ib_util.time_monitoring import get_time_drift_status
        
        echo(style(f"Measuring time drift with {samples} samples per server...", fg='yellow'))
        
        summary = get_time_drift_status(samples=samples)
        
        if summary is None:
            echo(style("Error: Unable to measure time drift", fg='red'))
            return
        
        if output_json:
            import json
            result = {
                'mean_ms': summary.mean_ms,
                'stdev_ms': summary.stdev_ms,
                'range_ms': summary.range_ms,
                'status': summary.status.value,
                'servers': summary.successful_servers,
                'timestamp': summary.timestamp.isoformat()
            }
            echo(json.dumps(result, indent=2))
        else:
            # Format human readable output
            echo(style("Time Drift Analysis", fg='cyan', bold=True))
            echo("=" * 40)
            echo(f"Mean drift:     {summary.mean_ms:+8.3f}ms")
            echo(f"Precision:      ±{summary.stdev_ms:7.3f}ms")
            echo(f"Range:          {summary.min_ms:+8.3f}ms to {summary.max_ms:+8.3f}ms")
            echo(f"Status:         {style(summary.status.value.upper(), fg='green' if summary.status.value in ['excellent', 'good'] else 'yellow')}")
            echo(f"NTP servers:    {summary.successful_servers}/5 responding")
            echo(f"Measurements:   {summary.total_measurements} total")
            
    except ImportError as e:
        echo(style(f"Error: Missing dependency - {e}", fg='red'))

@monitor.command('time-drift')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--verbose', '-v', is_flag=True, help='Show additional Chrony statistics')
def monitor_time_drift(output_json: bool, verbose: bool):
    """Check time drift using Chrony's superior internal tracking"""
    try:
        # Use Chrony's built-in tracking
        result = run_command(['chronyc', 'tracking'], check=False)
        if result.returncode != 0:
            echo(style("❌ Chrony not available, use 'ntp-time-drift' for legacy NTP monitoring", fg='red'))
            return
        
        lines = result.stdout.strip().split('\n') if isinstance(result.stdout, str) else result.stdout.decode().strip().split('\n')
        
        # Parse key values
        system_time_line = next((line for line in lines if 'System time' in line), None)
        rms_offset_line = next((line for line in lines if 'RMS offset' in line), None)
        frequency_line = next((line for line in lines if 'Frequency' in line), None)
        stratum_line = next((line for line in lines if 'Stratum' in line), None)
        
        if not system_time_line:
            echo(style("❌ Could not parse Chrony tracking data", fg='red'))
            return
        
        # Extract drift from "System time : 0.001580169 seconds fast of NTP time"
        parts = system_time_line.split(':')[1].strip().split()
        drift_seconds = float(parts[0])
        drift_ms = drift_seconds * 1000
        drift_direction = "fast" if "fast" in system_time_line else "slow"
        
        # Extract RMS precision
        rms_ms = 0
        if rms_offset_line:
            rms_parts = rms_offset_line.split(':')[1].strip().split()
            rms_ms = float(rms_parts[0]) * 1000
        
        # Extract frequency drift
        frequency_ppm = 0
        if frequency_line:
            freq_parts = frequency_line.split(':')[1].strip().split()
            frequency_ppm = float(freq_parts[0])
        
        # Extract stratum
        stratum = 0
        if stratum_line:
            stratum_parts = stratum_line.split(':')[1].strip()
            stratum = int(stratum_parts)
        
        # Determine status using consistent thresholds
        abs_drift = abs(drift_ms)
        if abs_drift < 1.0:  # EXCELLENT_MS
            status = "EXCELLENT"
            status_color = "green"
        elif abs_drift < 5.0:  # GOOD_MS
            status = "GOOD" 
            status_color = "green"
        elif abs_drift < 50.0:  # ACCEPTABLE_MS
            status = "ACCEPTABLE"
            status_color = "yellow"
        elif abs_drift < 500.0:  # POOR_MS
            status = "POOR"
            status_color = "yellow"
        else:
            status = "CRITICAL"
            status_color = "red"
        
        if output_json:
            result_data = {
                "drift_ms": round(drift_ms, 3),
                "drift_direction": drift_direction,
                "rms_precision_ms": round(rms_ms, 3),
                "frequency_ppm": frequency_ppm,
                "stratum": stratum,
                "status": status.lower(),
                "source": "chrony_internal",
                "timestamp": datetime.now().isoformat()
            }
            echo(json.dumps(result_data, indent=2))
        else:
            echo(style("Time Drift Analysis (Chrony Internal)", fg='cyan', bold=True))
            echo("=" * 45)
            echo(f"Current drift:   {drift_ms:+8.3f}ms ({drift_direction})")
            echo(f"RMS precision:   ±{rms_ms:7.3f}ms")
            echo(f"Status:          {style(status, fg=status_color, bold=True)}")
            echo(f"Stratum:         {stratum}")
            if verbose:
                echo(f"Frequency:       {frequency_ppm:+.3f} ppm")
                echo("Source:          Chrony internal tracking")
                echo("Accuracy:        Superior to NTP queries")
                
                # Show sources if verbose
                echo(style("\nNTP Sources:", fg='cyan'))
                sources_result = run_command(['chronyc', 'sources', '-v'], check=False)
                if sources_result.returncode == 0:
                    sources_output = sources_result.stdout if isinstance(sources_result.stdout, str) else sources_result.stdout.decode()
                    echo(sources_output)
        
    except Exception as e:
        echo(style(f"❌ Error accessing Chrony: {e}", fg='red'))
        echo("Use 'ntp-time-drift' for legacy NTP monitoring")

@monitor.command('sync-time')
def monitor_sync_time():
    """Synchronize system time with NTP servers"""
    try:
        from ib_util.time_monitoring import sync_time
        
        echo(style("Synchronizing system time...", fg='yellow'))
        
        success = sync_time()
        
        if success:
            echo(style("✓ Time synchronized successfully", fg='green'))
        else:
            echo(style("✗ Time synchronization failed", fg='red'))
            echo("Ensure you have sudo privileges and NTP tools are installed")
            
    except ImportError as e:
        echo(style(f"Error: Missing dependency - {e}", fg='red'))

@monitor.command('storage')
@click.option('--path', default='ib-stream/storage', help='Storage base path')
def monitor_storage(path: str):
    """Check current hour storage file status and activity"""
    try:
        from ib_util.storage_monitoring import get_current_hour_status, get_storage_health_status
        
        echo(style("Current Hour Storage Status", fg='cyan', bold=True))
        echo("=" * 60)
        
        # Get current hour status
        current_status = get_current_hour_status(path)
        current_hour = current_status['current_hour']
        
        echo(f"Hour:           {current_hour}")
        echo("")
        
        # V2 Status
        v2 = current_status['v2_protobuf']
        status_color = 'green' if v2['status'] == 'active' else 'yellow' if v2['status'] == 'stale' else 'red'
        echo(f"V2 Protobuf:    {style(v2['status'].upper(), fg=status_color, bold=True)}")
        echo(f"                Files: {v2['files']}, Size: {v2['size_mb']:.1f}MB")
        if v2['newest_age_seconds'] is not None:
            echo(f"                Last update: {v2['newest_age_seconds']:.1f}s ago")
        
        # V3 Status
        v3 = current_status['v3_protobuf']
        status_color = 'green' if v3['status'] == 'active' else 'yellow' if v3['status'] == 'stale' else 'red'
        echo(f"V3 Protobuf:    {style(v3['status'].upper(), fg=status_color, bold=True)}")
        echo(f"                Files: {v3['files']}, Size: {v3['size_mb']:.1f}MB")
        if v3['newest_age_seconds'] is not None:
            echo(f"                Last update: {v3['newest_age_seconds']:.1f}s ago")
        
        echo("=" * 60)
        
        # Overall status
        health = get_storage_health_status(path)['storage_streaming']
        health_color = 'green' if health['status'] == 'healthy' else 'yellow' if health['status'] == 'warning' else 'red'
        echo(f"Overall Status: {style(health['status'].upper(), fg=health_color, bold=True)}")
        
    except ImportError as e:
        echo(style(f"Error: Missing dependency - {e}", fg='red'))
    except Exception as e:
        echo(style(f"Error: {e}", fg='red'))

@monitor.command('storage-growth')
@click.option('--duration', '-d', default=60, help='Monitoring duration in seconds')
@click.option('--interval', '-i', default=5, help='Check interval in seconds') 
@click.option('--path', default='ib-stream/storage', help='Storage base path')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
def monitor_storage_growth(duration: int, interval: int, path: str, output_json: bool):
    """Monitor storage file growth over time to verify active streaming"""
    try:
        from ib_util.storage_monitoring import monitor_storage_growth as monitor_growth
        
        if not output_json:
            echo(style(f"Monitoring storage growth for {duration} seconds (checking every {interval}s)...", fg='yellow'))
        
        results = monitor_growth(path, duration_seconds=duration)
        
        if output_json:
            import json
            echo(json.dumps(results, indent=2))
        else:
            echo(style("Storage Growth Analysis", fg='cyan', bold=True))
            echo("=" * 60)
            echo(f"Monitoring Duration: {results['monitoring_duration_seconds']}s")
            echo(f"Checks Performed:    {results['checks_performed']}")
            echo(f"Data Streaming:      {style('YES' if results['is_streaming'] else 'NO', fg='green' if results['is_streaming'] else 'red', bold=True)}")
            echo("")
            
            # V2 Growth
            v2 = results['growth_summary']['v2_protobuf'] 
            echo(f"V2 Protobuf Growth:")
            echo(f"  Initial Size:      {v2['initial_size_mb']}MB")
            echo(f"  Final Size:        {v2['final_size_mb']}MB")
            echo(f"  Growth:            {v2['growth_mb']:+.2f}MB")
            echo(f"  Growth Rate:       {v2['growth_rate_mb_per_minute']:.2f}MB/min")
            echo(f"  File Count Change: {v2['file_count_change']:+d}")
            echo("")
            
            # V3 Growth  
            v3 = results['growth_summary']['v3_protobuf']
            echo(f"V3 Protobuf Growth:")
            echo(f"  Initial Size:      {v3['initial_size_mb']}MB")
            echo(f"  Final Size:        {v3['final_size_mb']}MB")
            echo(f"  Growth:            {v3['growth_mb']:+.2f}MB")
            echo(f"  Growth Rate:       {v3['growth_rate_mb_per_minute']:.2f}MB/min")
            echo(f"  File Count Change: {v3['file_count_change']:+d}")
            
    except ImportError as e:
        echo(style(f"Error: Missing dependency - {e}", fg='red'))
    except KeyboardInterrupt:
        echo(style("\nMonitoring interrupted by user", fg='yellow'))
    except Exception as e:
        echo(style(f"Error: {e}", fg='red'))


if __name__ == '__main__':
    cli()