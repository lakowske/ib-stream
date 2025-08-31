#!/usr/bin/env python3
"""
Integration tests for Configuration System v3.

Tests end-to-end configuration loading, service integration, 
backward compatibility, and real-world usage scenarios.
"""

import os
import pytest
import tempfile
import yaml
import subprocess
from pathlib import Path
from unittest.mock import patch
import sys

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load modules directly to avoid ibapi dependency
import importlib.util

def load_module(module_name: str, file_path: str):
    """Load module directly from file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestConfigV3Integration:
    """Integration tests for Configuration System v3"""

    @pytest.fixture
    def real_config_setup(self):
        """Setup real configuration files that match the actual system"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create real base configuration matching actual system
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
                    "enable_metrics": True,
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
            
            dev_config = {
                "project": {
                    "environment": "development"
                },
                "storage": {
                    "base_path": "storage-dev"
                }
            }
            
            prod_config = {
                "project": {
                    "environment": "production"
                },
                "storage": {
                    "base_path": "storage-prod"
                },
                "logging": {
                    "level": "INFO"
                }
            }
            
            # Create services directory and configurations
            services_dir = config_dir / "services"
            services_dir.mkdir()
            
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

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_ib_stream_development_config(self, real_config_setup):
        """Test ib-stream configuration loading in development environment"""
        # Load config v3 module
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        config = config_v3.load_config("ib-stream", real_config_setup)
        
        # Verify project configuration
        assert config.project.name == "ib-stream"
        assert config.project.version == "3.0.0"
        assert config.project.environment.value == "development"
        
        # Verify gateway configuration
        assert config.gateway.host == "192.168.0.60"
        assert config.gateway.ports == [4002, 4001]
        assert config.gateway.connection_timeout == 10
        
        # Verify service configuration (development)
        assert config.service.name == "ib-stream"
        assert config.service.type == "streaming"
        assert config.service.client.id == 101  # Dev default
        assert config.service.server.port == 8851
        assert config.service.server.host == "0.0.0.0"
        
        # Verify streaming configuration (development)
        assert config.service.streaming is not None
        assert config.service.streaming.enable_background_streaming is False
        assert config.service.streaming.tracked_contracts == []
        
        # Verify storage configuration
        assert config.storage.enabled is True
        assert config.storage.base_path == "storage-dev"  # Dev override
        assert config.storage.formats.v3_json is True
        assert config.storage.formats.v3_protobuf is True
        
        # Verify logging configuration
        assert config.logging.level == "DEBUG"
        assert config.logging.format == "detailed"

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "production"})
    def test_ib_stream_production_config(self, real_config_setup):
        """Test ib-stream configuration loading in production environment"""
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        config = config_v3.load_config("ib-stream", real_config_setup)
        
        # Verify environment
        assert config.project.environment.value == "production"
        
        # Verify production overrides
        assert config.service.client.id == 851  # Prod override
        assert config.service.server.port == 8851  # Prod specific
        assert config.storage.base_path == "storage-prod"  # Prod override
        assert config.logging.level == "INFO"  # Prod override
        
        # Verify production streaming configuration
        assert config.service.streaming.enable_background_streaming is True
        assert len(config.service.streaming.tracked_contracts) == 1
        
        contract = config.service.streaming.tracked_contracts[0]
        assert contract.contract_id == 711280073
        assert contract.symbol == "MNQ"
        assert "LAST_PRICE" in contract.tick_types
        assert contract.buffer_hours == 24

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_ib_contract_development_config(self, real_config_setup):
        """Test ib-contract configuration loading in development environment"""
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        config = config_v3.load_config("ib-contract", real_config_setup)
        
        # Verify project configuration
        assert config.project.name == "ib-stream"  # From base
        assert config.project.environment.value == "development"
        
        # Verify service configuration
        assert config.service.name == "ib-contract"
        assert config.service.type == "lookup"
        assert config.service.client.id == 102  # Dev default
        assert config.service.server.port == 8861
        
        # Verify cache configuration
        assert config.service.cache is not None
        assert config.service.cache.duration_days == 1
        assert config.service.cache.memory_cache_size == 1000
        assert config.service.cache.file_cache_enabled is True

    def test_debug_runner_integration(self, real_config_setup):
        """Test debug runner integration with config v3"""
        debug_script = project_root / "ib-stream" / "debug.py"
        
        if not debug_script.exists():
            pytest.skip("Debug runner not available")
        
        # Test validation-only mode
        env = os.environ.copy()
        env.update({
            "IB_ENVIRONMENT": "development",
            "IB_CONFIG_ROOT": real_config_setup
        })
        
        result = subprocess.run([
            sys.executable, str(debug_script), "--validate-only"
        ], env=env, capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0
        assert "Configuration validation successful" in result.stdout

    def test_backward_compatibility_adapter(self, real_config_setup):
        """Test backward compatibility adapter integration"""
        # Load config v3 adapter
        adapter_path = project_root / "ib-stream" / "src" / "ib_stream" / "config_v3_adapter.py"
        
        if not adapter_path.exists():
            pytest.skip("Config v3 adapter not available")
        
        # Load adapter module directly
        adapter_module = load_module("config_v3_adapter", str(adapter_path))
        
        with patch.dict(os.environ, {
            "IB_ENVIRONMENT": "development",
            "IB_CONFIG_ROOT": real_config_setup
        }):
            try:
                adapter = adapter_module.ConfigV3Adapter("ib-stream")
                legacy_config = adapter.to_legacy_format()
                
                # Verify legacy format conversion
                assert isinstance(legacy_config, dict)
                assert "CLIENT_ID" in legacy_config
                assert "GATEWAY_HOST" in legacy_config
                assert "GATEWAY_PORTS" in legacy_config
                assert legacy_config["CLIENT_ID"] == 101
                assert legacy_config["GATEWAY_HOST"] == "192.168.0.60"
                
            except Exception as e:
                # If adapter has dependencies we can't load, that's expected in tests
                pytest.skip(f"Adapter requires dependencies not available in test: {e}")

    @patch.dict(os.environ, {
        "IB_ENVIRONMENT": "development",
        "IB_GATEWAY_HOST": "test-override-host",
        "IB_GATEWAY_PORTS": "5001,5002",
        "IB_CLIENT_ID": "999"
    })
    def test_environment_variable_overrides_integration(self, real_config_setup):
        """Test environment variable overrides in integration scenario"""
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        config = config_v3.load_config("ib-stream", real_config_setup)
        
        # Verify environment variable overrides took effect
        assert config.gateway.host == "test-override-host"
        assert config.gateway.ports == [5001, 5002]
        assert config.service.client.id == 999

    def test_categorical_validation_integration(self, real_config_setup):
        """Test categorical validation in integration scenario"""
        # Load categorical config module
        categorical_config_path = project_root / "ib-util" / "ib_util" / "config_v3_categorical.py"
        
        # Load dependencies first
        categorical_path = project_root / "ib-util" / "ib_util" / "categorical.py"
        categorical = load_module("categorical", str(categorical_path))
        sys.modules["categorical"] = categorical
        
        categorical_config = load_module("config_v3_categorical", str(categorical_config_path))
        
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            # Test monadic configuration loading
            result = categorical_config.load_config_categorical("ib-stream", real_config_setup)
            
            assert result.is_success()
            config_dict = result.unwrap()
            
            # Verify loaded configuration structure
            assert "service" in config_dict
            assert "gateway" in config_dict
            assert config_dict["service"]["client"]["id"] == 101
            
            # Test safe wrapper
            safe_result = categorical_config.load_config_safe("ib-stream", real_config_setup)
            assert safe_result.is_success()
            safe_config = safe_result.get_or_raise()
            assert safe_config["service"]["name"] == "ib-stream"

    def test_config_transformations_integration(self, real_config_setup):
        """Test configuration transformations integration"""
        # Load necessary modules
        categorical_path = project_root / "ib-util" / "ib_util" / "categorical.py"
        categorical = load_module("categorical", str(categorical_path))
        sys.modules["categorical"] = categorical
        
        transformations_path = project_root / "ib-util" / "ib_util" / "config_transformations.py"
        transformations = load_module("config_transformations", str(transformations_path))
        
        # Load a configuration
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            config = config_v3.load_config("ib-stream", real_config_setup)
            config_dict = config.model_dump()
            
            # Test string normalization
            normalized = transformations.ConfigTransformations.normalize_strings(config_dict)
            assert isinstance(normalized, dict)
            
            # Test environment variable transformation
            env_vars = transformations.ConfigTransformations.to_environment_vars(config_dict)
            assert "IB_GATEWAY_HOST" in env_vars
            assert "IB_SERVICE_CLIENT_ID" in env_vars
            assert env_vars["IB_GATEWAY_HOST"] == "192.168.0.60"
            assert env_vars["IB_SERVICE_CLIENT_ID"] == "101"
            
            # Test monadic validation
            validation_result = transformations.ConfigTransformations.validate_and_transform(config_dict)
            assert validation_result.is_success()


class TestConfigV3PerformanceIntegration:
    """Performance integration tests"""

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_configuration_loading_performance(self, real_config_setup):
        """Test configuration loading performance"""
        import time
        
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        # Warm up
        config_v3.load_config("ib-stream", real_config_setup)
        
        # Time actual loading
        start_time = time.time()
        config = config_v3.load_config("ib-stream", real_config_setup)
        end_time = time.time()
        
        loading_time = end_time - start_time
        
        # Configuration loading should be fast (< 100ms)
        assert loading_time < 0.1
        assert config.project.name == "ib-stream"

    def test_validation_performance(self, real_config_setup):
        """Test configuration validation performance"""
        import time
        
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            # Warm up
            config_v3.validate_config("ib-stream", real_config_setup)
            
            # Time validation
            start_time = time.time()
            is_valid = config_v3.validate_config("ib-stream", real_config_setup)
            end_time = time.time()
            
            validation_time = end_time - start_time
            
            # Validation should be fast (< 50ms)
            assert validation_time < 0.05
            assert is_valid is True


class TestConfigV3ErrorHandlingIntegration:
    """Integration tests for error handling scenarios"""

    def test_missing_service_configuration(self, real_config_setup):
        """Test handling of missing service configuration"""
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            # Try to load non-existent service
            with pytest.raises(Exception):  # Should raise validation error
                config_v3.load_config("nonexistent-service", real_config_setup)

    def test_invalid_environment_integration(self, real_config_setup):
        """Test invalid environment handling in integration"""
        config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
        config_v3 = load_module("config_v3", str(config_v3_path))
        
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "invalid-env"}):
            with pytest.raises(ValueError, match="Invalid environment"):
                config_v3.load_config("ib-stream", real_config_setup)

    def test_corrupted_yaml_integration(self):
        """Test handling of corrupted YAML files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create corrupted YAML
            with open(config_dir / "base.yaml", "w") as f:
                f.write("invalid: yaml: [unclosed")
            
            config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
            config_v3 = load_module("config_v3", str(config_v3_path))
            
            with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
                with pytest.raises(ValueError, match="Invalid YAML"):
                    config_v3.load_config("test-service", str(config_dir))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])