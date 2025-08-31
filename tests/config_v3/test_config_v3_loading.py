#!/usr/bin/env python3
"""
Unit tests for Configuration System v3 loading and validation.

Tests the configuration loading pipeline, YAML parsing, environment
detection, and Pydantic model validation.
"""

import os
import pytest
import tempfile
import yaml
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

# Load configuration modules
config_v3_path = project_root / "ib-util" / "ib_util" / "config_v3.py"
config_v3 = load_module("config_v3", str(config_v3_path))

# Import classes and functions
ConfigLoader = config_v3.ConfigLoader
load_config = config_v3.load_config
validate_config = config_v3.validate_config
Environment = config_v3.Environment


class TestConfigurationLoading:
    """Test configuration loading and validation"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary configuration directory with test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create base configuration
            base_config = {
                "project": {
                    "name": "test-service",
                    "version": "3.0.0"
                },
                "gateway": {
                    "host": "localhost",
                    "ports": [4002, 4001],
                    "connection_timeout": 10,
                    "reconnect_attempts": 3
                },
                "storage": {
                    "enabled": True,
                    "base_path": "test-storage",
                    "formats": {
                        "v2_json": False,
                        "v2_protobuf": False,
                        "v3_json": True,
                        "v3_protobuf": True
                    },
                    "buffer_size": 50,
                    "max_file_size_mb": 10
                },
                "logging": {
                    "level": "DEBUG",
                    "format": "detailed"
                },
                "performance": {
                    "max_concurrent_streams": 5
                }
            }
            
            # Create development environment overrides
            dev_config = {
                "project": {
                    "environment": "development"
                },
                "storage": {
                    "base_path": "test-storage-dev",
                    "enable_metrics": True
                },
                "logging": {
                    "level": "DEBUG"
                }
            }
            
            # Create production environment overrides
            prod_config = {
                "project": {
                    "environment": "production"
                },
                "storage": {
                    "base_path": "test-storage-prod"
                },
                "logging": {
                    "level": "INFO"
                }
            }
            
            # Create service-specific configuration
            services_dir = config_dir / "services"
            services_dir.mkdir()
            
            service_config = {
                "service": {
                    "name": "test-service",
                    "type": "streaming",
                    "client": {"id": 101},
                    "server": {
                        "host": "0.0.0.0",
                        "port": 8851
                    }
                },
                "development": {
                    "service": {
                        "client": {"id": 201}
                    }
                },
                "production": {
                    "service": {
                        "client": {"id": 801},
                        "server": {"port": 8851}
                    }
                }
            }
            
            # Write configuration files
            with open(config_dir / "base.yaml", "w") as f:
                yaml.dump(base_config, f, default_flow_style=False)
                
            with open(config_dir / "development.yaml", "w") as f:
                yaml.dump(dev_config, f, default_flow_style=False)
                
            with open(config_dir / "production.yaml", "w") as f:
                yaml.dump(prod_config, f, default_flow_style=False)
                
            with open(services_dir / "test-service.yaml", "w") as f:
                yaml.dump(service_config, f, default_flow_style=False)
            
            yield str(config_dir)

    def test_config_loader_initialization(self, temp_config_dir):
        """Test ConfigLoader initialization"""
        loader = ConfigLoader(temp_config_dir)
        assert loader.config_root == Path(temp_config_dir)
        
        # Test default initialization
        with patch.dict(os.environ, {"PWD": str(project_root)}):
            default_loader = ConfigLoader()
            expected_path = Path("config")
            # ConfigLoader should handle missing config directory gracefully

    def test_yaml_file_loading(self, temp_config_dir):
        """Test YAML file loading"""
        loader = ConfigLoader(temp_config_dir)
        
        # Load existing file
        base_result = loader.load_yaml_file(Path(temp_config_dir) / "base.yaml")
        assert base_result.is_success()
        base_data = base_result.unwrap()
        assert base_data["project"]["name"] == "test-service"
        assert base_data["gateway"]["host"] == "localhost"
        
        # Load non-existent file (should return empty dict)
        missing_result = loader.load_yaml_file(Path(temp_config_dir) / "missing.yaml")
        assert missing_result.is_success()
        assert missing_result.unwrap() == {}

    def test_config_merging(self, temp_config_dir):
        """Test configuration merging with monoid operations"""
        loader = ConfigLoader(temp_config_dir)
        
        base_config = {"server": {"host": "localhost", "port": 8080}, "debug": True}
        override_config = {"server": {"port": 9000, "timeout": 30}, "new_key": "new_value"}
        
        merged = loader.merge_configs(base_config, override_config)
        
        expected = {
            "server": {"host": "localhost", "port": 9000, "timeout": 30},
            "debug": True,
            "new_key": "new_value"
        }
        
        assert merged == expected

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_environment_detection_development(self):
        """Test environment detection - development"""
        loader = ConfigLoader()
        env_result = loader.get_environment()
        assert env_result.is_success()
        assert env_result.unwrap() == Environment.DEVELOPMENT

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "production"})
    def test_environment_detection_production(self):
        """Test environment detection - production"""
        loader = ConfigLoader()
        env_result = loader.get_environment()
        assert env_result.is_success()
        assert env_result.unwrap() == Environment.PRODUCTION

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "staging"})
    def test_environment_detection_invalid(self):
        """Test environment detection - invalid environment"""
        loader = ConfigLoader()
        env_result = loader.get_environment()
        assert env_result.is_error()
        assert "Invalid environment: staging" in env_result.error()

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_service_config_loading_development(self, temp_config_dir):
        """Test complete service configuration loading - development"""
        config = load_config("test-service", temp_config_dir)
        
        # Check basic project settings
        assert config.project.name == "test-service"
        assert config.project.environment == Environment.DEVELOPMENT
        
        # Check gateway settings from base
        assert config.gateway.host == "localhost" 
        assert config.gateway.ports == [4002, 4001]
        assert config.gateway.connection_timeout == 10
        
        # Check storage settings (dev overrides)
        assert config.storage.enabled is True
        assert config.storage.base_path == "test-storage-dev"  # Dev override
        assert config.storage.enable_metrics is True  # Dev specific
        
        # Check logging (dev overrides)
        assert config.logging.level == "DEBUG"  # Dev override
        assert config.logging.format == "detailed"
        
        # Check service settings (dev overrides)
        assert config.service.name == "test-service"
        assert config.service.type == "streaming"
        assert config.service.client.id == 201  # Dev override
        assert config.service.server.port == 8851
        assert config.service.server.host == "0.0.0.0"

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "production"})  
    def test_service_config_loading_production(self, temp_config_dir):
        """Test complete service configuration loading - production"""
        config = load_config("test-service", temp_config_dir)
        
        # Check environment
        assert config.project.environment == Environment.PRODUCTION
        
        # Check production overrides
        assert config.storage.base_path == "test-storage-prod"  # Prod override
        assert config.logging.level == "INFO"  # Prod override
        assert config.service.client.id == 801  # Prod override
        assert config.service.server.port == 8851  # Prod specific

    @patch.dict(os.environ, {
        "IB_ENVIRONMENT": "development",
        "IB_GATEWAY_HOST": "custom-host",
        "IB_GATEWAY_PORTS": "5002,5001",
        "IB_CLIENT_ID": "999",
        "IB_SERVER_PORT": "9999"
    })
    def test_environment_variable_overrides(self, temp_config_dir):
        """Test environment variable overrides"""
        config = load_config("test-service", temp_config_dir)
        
        # Check environment variable overrides
        assert config.gateway.host == "custom-host"
        assert config.gateway.ports == [5002, 5001]
        assert config.service.client.id == 999
        assert config.service.server.port == 9999

    def test_validation_success(self, temp_config_dir):
        """Test configuration validation - success case"""
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            is_valid = validate_config("test-service", temp_config_dir)
            assert is_valid is True

    def test_validation_failure_missing_service(self, temp_config_dir):
        """Test configuration validation - missing service"""
        with patch.dict(os.environ, {"IB_ENVIRONMENT": "development"}):
            is_valid = validate_config("nonexistent-service", temp_config_dir)
            assert is_valid is False


class TestConfigurationValidation:
    """Test configuration validation and error handling"""

    @pytest.fixture
    def invalid_config_dir(self):
        """Create configuration directory with invalid data"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create base config with invalid data
            invalid_config = {
                "project": {"name": "test"},
                "gateway": {
                    "host": "localhost",
                    "ports": [80, 70000]  # Invalid ports
                },
                "logging": {
                    "level": "INVALID_LEVEL"  # Invalid log level
                },
                "service": {
                    "name": "test",
                    "type": "test",
                    "client": {"id": 9999999},  # Invalid client ID
                    "server": {"port": 80}  # Invalid server port
                }
            }
            
            with open(config_dir / "base.yaml", "w") as f:
                yaml.dump(invalid_config, f)
                
            # Create minimal required files
            Path(config_dir / "development.yaml").touch()
            services_dir = config_dir / "services"
            services_dir.mkdir()
            Path(services_dir / "test.yaml").touch()
            
            yield str(config_dir)

    @patch.dict(os.environ, {"IB_ENVIRONMENT": "development"})
    def test_validation_with_invalid_data(self, invalid_config_dir):
        """Test validation catches invalid data"""
        # This should fail validation due to invalid ports, client ID, etc.
        is_valid = validate_config("test", invalid_config_dir)
        assert is_valid is False

    def test_malformed_yaml(self):
        """Test handling of malformed YAML files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create malformed YAML
            with open(config_dir / "base.yaml", "w") as f:
                f.write("invalid: yaml: content: [unclosed")
            
            loader = ConfigLoader(str(config_dir))
            result = loader.load_yaml_file(config_dir / "base.yaml")
            
            assert result.is_error()
            assert "Invalid YAML" in result.error()


class TestConfigurationEdgeCases:
    """Test edge cases and error conditions"""

    def test_missing_config_directory(self):
        """Test behavior with missing configuration directory"""
        with pytest.raises(FileNotFoundError, match="Configuration directory not found"):
            ConfigLoader("/nonexistent/config/directory")

    @patch.dict(os.environ, {}, clear=True)
    def test_default_environment(self):
        """Test default environment when IB_ENVIRONMENT not set"""
        loader = ConfigLoader()
        env_result = loader.get_environment()
        assert env_result.is_success()
        assert env_result.unwrap() == Environment.DEVELOPMENT  # Default

    def test_empty_yaml_file(self):
        """Test handling of empty YAML files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            # Create empty YAML file
            empty_file = config_dir / "empty.yaml"
            empty_file.touch()
            
            loader = ConfigLoader(str(config_dir))
            result = loader.load_yaml_file(empty_file)
            
            assert result.is_success()
            assert result.unwrap() == {}

    @patch.dict(os.environ, {"IB_GATEWAY_PORTS": "invalid,port,list"})
    def test_invalid_environment_variable_format(self, temp_config_dir):
        """Test handling of invalid environment variable formats"""
        # Create minimal config to load
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            
            base_config = {
                "project": {"name": "test"},
                "service": {"name": "test", "type": "test"}
            }
            
            with open(config_dir / "base.yaml", "w") as f:
                yaml.dump(base_config, f)
            
            Path(config_dir / "development.yaml").touch()
            services_dir = config_dir / "services"
            services_dir.mkdir()
            Path(services_dir / "test.yaml").touch()
            
            with patch.dict(os.environ, {
                "IB_ENVIRONMENT": "development",
                "IB_GATEWAY_PORTS": "invalid,ports"
            }):
                # This should handle the invalid port format gracefully
                is_valid = validate_config("test", str(config_dir))
                assert is_valid is False  # Should fail due to invalid ports


if __name__ == "__main__":
    pytest.main([__file__, "-v"])