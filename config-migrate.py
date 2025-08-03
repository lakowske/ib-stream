#!/usr/bin/env python3
"""
Configuration migration script.

Migrates from the current shell-based configuration system to the new
Python-based system with Pydantic validation and dotenv loading.
"""

import os
import sys
from pathlib import Path

# Add the project to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ib_util.config import (
    IBEnvironment, 
    load_orchestration_for_environment,
    validate_configuration,
    ConfigLoader
)


def main():
    """Main migration function."""
    print("IB Configuration Migration Tool")
    print("=" * 40)
    
    # Check current status
    print("\n1. Validating current configuration...")
    results = validate_configuration()
    
    if results.get('warnings'):
        print("Warnings found:")
        for warning in results['warnings']:
            print(f"  • {warning}")
    
    # Create new configuration structure
    print("\n2. Creating new configuration structure...")
    
    config_dir = project_root / "config"
    config_dir.mkdir(exist_ok=True)
    
    # Migrate production environment
    print("\n3. Migrating production configuration...")
    
    try:
        loader = ConfigLoader(str(project_root))
        
        # Load legacy production file
        legacy_prod_file = project_root / "ib-stream" / "config" / "production-server.env"
        if legacy_prod_file.exists():
            print(f"Loading legacy file: {legacy_prod_file}")
            loader.load_legacy_env_file(str(legacy_prod_file))
        
        # Create new production environment file
        new_prod_file = config_dir / ".env.production"
        with open(new_prod_file, 'w') as f:
            f.write("# Production configuration for IB services\n")
            f.write("# Migrated from legacy configuration files\n\n")
            f.write("# Environment\n")
            f.write("IB_ENVIRONMENT=production\n\n")
            f.write("# TWS Connection (localhost on production server)\n")
            f.write("IB_HOST=localhost\n")
            f.write("IB_PORTS=4002\n\n")
            f.write("# Storage (full production setup)\n")
            f.write("IB_STREAM_ENABLE_STORAGE=true\n")
            f.write("IB_STREAM_ENABLE_JSON=true\n")
            f.write("IB_STREAM_ENABLE_PROTOBUF=true\n")
            f.write("IB_STREAM_ENABLE_POSTGRES=true\n")
            f.write("IB_STREAM_ENABLE_METRICS=true\n")
            f.write("IB_STREAM_ENABLE_BACKGROUND_STREAMING=true\n")
            f.write("IB_STREAM_TRACKED_CONTRACTS=711280073:MNQ:bid_ask;last:24\n\n")
            f.write("# Performance\n")
            f.write("IB_STREAM_MAX_STREAMS=100\n")
            f.write("IB_STREAM_BUFFER_SIZE=1000\n\n")
        
        print(f"✓ Created: {new_prod_file}")
        
        # Create development configuration
        dev_file = config_dir / ".env.development"
        with open(dev_file, 'w') as f:
            f.write("# Development configuration for IB services\n\n")
            f.write("# Environment\n")
            f.write("IB_ENVIRONMENT=development\n\n")
            f.write("# TWS Connection (remote gateway for development)\n")
            f.write("IB_HOST=192.168.0.60\n")
            f.write("IB_PORTS=4002\n\n")
            f.write("# Storage (lighter setup for development)\n")
            f.write("IB_STREAM_ENABLE_STORAGE=true\n")
            f.write("IB_STREAM_ENABLE_JSON=true\n")
            f.write("IB_STREAM_ENABLE_PROTOBUF=false\n")
            f.write("IB_STREAM_ENABLE_POSTGRES=false\n")  
            f.write("IB_STREAM_ENABLE_BACKGROUND_STREAMING=false\n\n")
            f.write("# Performance\n")
            f.write("IB_STREAM_MAX_STREAMS=10\n")
            f.write("IB_STREAM_BUFFER_SIZE=100\n\n")
        
        print(f"✓ Created: {dev_file}")
        
        # Generate orchestration configurations
        print("\n4. Generating orchestration configurations...")
        
        for env in [IBEnvironment.PRODUCTION, IBEnvironment.DEVELOPMENT]:
            print(f"Generating {env.value} orchestration...")
            
            # Set environment for loading
            os.environ["IB_ENVIRONMENT"] = env.value
            
            orch_config = load_orchestration_for_environment(env, str(project_root))
            supervisor_config = orch_config.to_supervisor_config()
            
            supervisor_file = project_root / f"supervisor-{env.value}.conf"
            with open(supervisor_file, 'w') as f:
                f.write(supervisor_config)
            
            print(f"✓ Created: {supervisor_file}")
            
            # Show configuration summary
            configs = orch_config.get_all_service_configs()
            print(f"  Services configured:")
            for service_name, config in configs.items():
                print(f"    • {service_name}: port {config.server.port}, client_id {config.connection.client_id}")
        
        print("\n5. Creating new Makefile targets...")
        
        # Create a simple replacement makefile section
        new_makefile_section = """
# New Configuration Management (using ib-util)
config-validate:
	@echo "Validating configuration..."
	.venv/bin/python -c "from ib_util.config.cli import config_cli; import sys; sys.argv=['config-cli', 'validate']; config_cli()"

config-show-production:
	@echo "Production configuration:"
	.venv/bin/python -c "from ib_util.config.cli import config_cli; import sys; sys.argv=['config-cli', 'show', '--service', 'ib-stream', '--environment', 'production']; config_cli()"

start-production-new:
	@echo "Starting production services with new configuration system..."
	IB_ENVIRONMENT=production .venv/bin/supervisord -c supervisor-production.conf

start-development-new:
	@echo "Starting development services with new configuration system..."  
	IB_ENVIRONMENT=development .venv/bin/supervisord -c supervisor-development.conf

# Legacy targets (keep for transition)
start-production-legacy: start-production
start-development-legacy: start-supervisor
"""
        
        makefile_addition = project_root / "Makefile.new-config"
        with open(makefile_addition, 'w') as f:
            f.write(new_makefile_section)
        
        print(f"✓ Created: {makefile_addition}")
        print("  Add this content to your main Makefile")
        
        print("\n✓ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Review the generated configuration files")
        print("2. Test with: make config-validate")
        print("3. Test production startup: make start-production-new")
        print("4. Once tested, replace legacy targets in Makefile")
        print("5. Remove legacy configuration files")
        
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()