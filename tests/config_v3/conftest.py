"""
Pytest configuration for Configuration System v3 tests.

Provides common fixtures and test configuration for all config v3 tests.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
import sys
import os

# Add project root to Python path for all tests
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Test markers for different test categories
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "config_v3: Configuration System v3 tests"
    )
    config.addinivalue_line(
        "markers", "categorical: Category Theory structure tests" 
    )
    config.addinivalue_line(
        "markers", "property_based: Property-based tests using hypothesis"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring full system"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and timing tests"
    )


@pytest.fixture
def sample_config_hierarchy():
    """
    Create a complete sample configuration hierarchy for testing.
    
    Returns path to temporary directory containing:
    - base.yaml (shared configuration)
    - development.yaml (dev environment overrides)
    - production.yaml (prod environment overrides)  
    - services/ib-stream.yaml (ib-stream service config)
    - services/ib-contract.yaml (ib-contract service config)
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)
        
        # Base configuration (shared across all environments/services)
        base_config = {
            "project": {
                "name": "ib-stream",
                "version": "3.0.0"
            },
            "gateway": {
                "host": "192.168.0.60",
                "ports": [4002, 4001],
                "connection_timeout": 10,
                "reconnect_attempts": 5
            },
            "storage": {
                "enabled": True,
                "formats": {
                    "v2_json": False,
                    "v2_protobuf": False,
                    "v3_json": True,
                    "v3_protobuf": True
                },
                "enable_postgres": False,
                "buffer_size": 100,
                "max_file_size_mb": 100
            },
            "logging": {
                "level": "DEBUG",
                "format": "detailed",
                "file_rotation": "daily"
            },
            "performance": {
                "max_concurrent_streams": 10,
                "default_timeout_seconds": None
            }
        }
        
        # Development environment overrides
        dev_config = {
            "project": {
                "environment": "development"
            },
            "storage": {
                "base_path": "storage-dev",
                "enable_metrics": True
            },
            "logging": {
                "level": "DEBUG"
            }
        }
        
        # Production environment overrides
        prod_config = {
            "project": {
                "environment": "production"
            },
            "storage": {
                "base_path": "storage-prod",
                "enable_metrics": True
            },
            "logging": {
                "level": "INFO"
            }
        }
        
        # Create services directory
        services_dir = config_dir / "services"
        services_dir.mkdir()
        
        # ib-stream service configuration
        ib_stream_config = {
            "service": {
                "name": "ib-stream",
                "type": "streaming",
                "server": {
                    "host": "0.0.0.0",
                    "port": 8851
                },
                "client": {
                    "id": 101
                }
            },
            "streaming": {
                "enable_background_streaming": False,
                "tracked_contracts": []
            },
            # Environment-specific overrides within service config
            "development": {
                "streaming": {
                    "enable_background_streaming": False
                }
            },
            "production": {
                "service": {
                    "client": {"id": 851},
                    "server": {"port": 8851}
                },
                "streaming": {
                    "enable_background_streaming": True,
                    "tracked_contracts": [
                        {
                            "contract_id": 711280073,
                            "symbol": "MNQ",
                            "tick_types": ["LAST_PRICE", "VOLUME", "BID_ASK"],
                            "buffer_hours": 24
                        }
                    ]
                }
            }
        }
        
        # ib-contract service configuration
        ib_contract_config = {
            "service": {
                "name": "ib-contract",
                "type": "lookup",
                "server": {
                    "host": "0.0.0.0",
                    "port": 8861
                },
                "client": {
                    "id": 102
                },
                "cache": {
                    "duration_days": 1,
                    "memory_cache_size": 1000,
                    "file_cache_enabled": True
                }
            },
            "production": {
                "service": {
                    "client": {"id": 852},
                    "server": {"port": 8861}
                }
            }
        }
        
        # Write all configuration files
        with open(config_dir / "base.yaml", "w") as f:
            yaml.dump(base_config, f, default_flow_style=False)
            
        with open(config_dir / "development.yaml", "w") as f:
            yaml.dump(dev_config, f, default_flow_style=False)
            
        with open(config_dir / "production.yaml", "w") as f:
            yaml.dump(prod_config, f, default_flow_style=False)
            
        with open(services_dir / "ib-stream.yaml", "w") as f:
            yaml.dump(ib_stream_config, f, default_flow_style=False)
            
        with open(services_dir / "ib-contract.yaml", "w") as f:
            yaml.dump(ib_contract_config, f, default_flow_style=False)
        
        yield str(config_dir)


@pytest.fixture 
def clean_environment():
    """
    Provide a clean environment for configuration tests.
    
    Clears relevant environment variables and restores them after test.
    """
    # Environment variables that affect configuration loading
    env_vars = [
        'IB_ENVIRONMENT',
        'IB_CONFIG_ROOT',
        'IB_GATEWAY_HOST',
        'IB_GATEWAY_PORTS',
        'IB_CLIENT_ID',
        'IB_SERVER_PORT'
    ]
    
    # Save original values
    original_values = {}
    for var in env_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]
    
    yield
    
    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def module_loader():
    """
    Utility fixture for loading modules directly from file paths.
    
    Useful for loading configuration modules without ibapi dependencies.
    """
    import importlib.util
    
    def load_module(module_name: str, file_path: str):
        """Load module directly from file path"""
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    return load_module


# Skip property-based tests if hypothesis not available
def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle missing dependencies"""
    try:
        import hypothesis
    except ImportError:
        skip_hypothesis = pytest.mark.skip(reason="hypothesis not available")
        for item in items:
            if "property_based" in item.keywords or "test_categorical_properties" in str(item.fspath):
                item.add_marker(skip_hypothesis)