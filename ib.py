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
from pathlib import Path
from typing import Optional, List

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
        from ib_util.config.compat import validate_migration
        result = validate_migration()
        
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
                echo(f"  Host: {getattr(config, 'host', 'N/A')}")
                echo(f"  Client ID: {getattr(config, 'client_id', 'N/A')}")
                echo(f"  Server Port: {getattr(config, 'server_port', 'N/A')}")
                echo(f"  Storage: {getattr(getattr(config, 'storage', None), 'enable_storage', 'N/A')}")
                
        except Exception as e:
            echo(style(f"  Error loading configuration: {e}", fg='red'))


@config.command()
@click.option('--service', type=click.Choice(['ib-stream', 'ib-contract', 'all']), 
              default='all', help='Service to watch')
def watch(service):
    """Watch configuration files for changes (hot-reload)"""
    ensure_venv()
    
    if service == 'all':
        service_arg = []
    else:
        service_arg = ['--service', service]
    
    echo(style("Starting configuration watcher...", fg='yellow'))
    echo("Edit .env files in ib-stream/config/ to see real-time changes")
    echo("Press Ctrl+C to stop")
    echo()
    
    run_command([str(VENV_PYTHON), 'config-watch.py'] + service_arg, check=False)


@config.command()
@click.argument('service1', type=click.Choice(['ib-stream', 'ib-contract']))
@click.argument('service2', type=click.Choice(['ib-stream', 'ib-contract']))
def compare(service1, service2):
    """Compare configurations between services"""
    ensure_venv()
    
    run_command([str(VENV_PYTHON), 'config-diff.py', 'compare', service1, service2])


@config.command()
def summary():
    """Show configuration summary for all services"""
    ensure_venv()
    
    run_command([str(VENV_PYTHON), 'config-diff.py', 'summary'])


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


def get_supervisorctl(config_file: str = None):
    """Get the supervisorctl path with proper configuration"""
    # Set required environment variables for supervisor config
    env = os.environ.copy()
    env['PROJECT_ROOT'] = str(PROJECT_ROOT)
    env['USER'] = os.getenv('USER', 'unknown')
    
    # Use specified config file or determine automatically
    if config_file is None:
        # Use production supervisor config if it exists and has running services
        production_config = PROJECT_ROOT / 'supervisor-production.conf'
        config_file = 'supervisor-production.conf' if production_config.exists() else 'supervisor.conf'
    
    return ([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisorctl'), '-c', config_file], env)


@services.command()
@click.option('--environment', type=click.Choice(['development', 'production']), 
              default='production', help='Target environment')
def start(environment):
    """Start services with supervisor"""
    ensure_venv()
    ensure_supervisor_config()
    
    echo(style(f"Starting services in {environment} mode...", fg='yellow'))
    
    # Set environment variables
    env = os.environ.copy()
    env['PROJECT_ROOT'] = str(PROJECT_ROOT)
    env['USER'] = os.getenv('USER', 'unknown')
    
    # Determine which supervisor config to use based on environment
    config_file = 'supervisor-production.conf' if environment == 'production' else 'supervisor.conf'
    socket_file = PROJECT_ROOT / 'supervisor.sock'
    
    # Clean up stale socket file if supervisor isn't actually running
    import subprocess
    if socket_file.exists():
        try:
            test_result = subprocess.run([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisorctl'), '-c', config_file, 'status'], 
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
        result = subprocess.run([str(PROJECT_ROOT / '.venv' / 'bin' / 'supervisord'), '-c', config_file], 
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
    
    # Start all programs
    echo(style("Starting services...", fg='green'))
    cmd, env = get_supervisorctl(config_file)
    
    result = subprocess.run(cmd + ['start', 'all'], capture_output=True, text=True, env=env)
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
    env['IB_HOST'] = 'localhost'
    env['IB_PORTS'] = '[4002]'
    env['IB_CLIENT_ID'] = '777'  # Use unique client ID for testing
    env['IB_ENVIRONMENT'] = 'test'
    
    # Simple connection test using StreamingApp directly
    cmd = [str(VENV_PYTHON), '-c', """
import sys; sys.path.insert(0, 'ib-stream/src')
import os, time
from ib_stream.streaming_app import StreamingApp
from ib_stream.config_v2 import create_config

# Set test environment variables for config
os.environ['IB_HOST'] = 'localhost'
os.environ['IB_PORTS'] = '[4002]'
os.environ['IB_CLIENT_ID'] = '777'
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

@monitor.command('time-drift')
@click.option('--samples', '-s', default=5, help='Number of samples per server')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
def monitor_time_drift(samples: int, output_json: bool):
    """Check high-precision time drift against NTP servers"""
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