"""
Multi-service orchestration configuration.

Handles coordination of multiple IB services (ib-stream, ib-contract, etc.)
with shared resources, port allocation, and environment management.
"""

import hashlib
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from .base import IBEnvironment, IBBaseConfig, IBConnectionConfig, IBServerConfig, IBStorageConfig


class ServiceType(str, Enum):
    """Supported service types."""
    STREAM = "ib-stream"
    CONTRACT = "ib-contract"
    STUDIES = "ib-studies"


class ServiceConfig(BaseModel):
    """Configuration for a single service in the orchestration."""
    
    name: ServiceType = Field(description="Service type")
    enabled: bool = Field(default=True, description="Whether service is enabled")
    port_offset: int = Field(default=0, description="Port offset from base port")
    client_id_offset: int = Field(default=0, description="Client ID offset from base client ID")
    replicas: int = Field(default=1, description="Number of service replicas")
    
    # Service-specific overrides
    config_overrides: Dict[str, Any] = Field(default_factory=dict, description="Service-specific config overrides")
    
    @field_validator('replicas')
    @classmethod
    def validate_replicas(cls, v):
        """Ensure replica count is reasonable."""
        if not (1 <= v <= 10):
            raise ValueError(f"Replica count must be between 1 and 10, got: {v}")
        return v


class IBOrchestrationConfig(BaseModel):
    """
    Orchestration configuration for multiple IB services.
    
    This handles:
    - Multi-service deployment with shared configurations
    - Automatic port and client ID allocation
    - Environment-specific settings
    - Instance isolation using path-based hashing
    """
    
    # Environment and identification
    environment: IBEnvironment = Field(default=IBEnvironment.DEVELOPMENT)
    deployment_name: str = Field(default="ib-platform", description="Name for this deployment")
    project_root: str = Field(description="Root directory of the project")
    
    # Base configuration that services inherit from
    base_config: IBBaseConfig = Field(description="Base configuration for all services")
    
    # Service definitions
    services: Dict[str, ServiceConfig] = Field(description="Service configurations")
    
    # Orchestration settings
    enable_service_discovery: bool = Field(default=True, description="Enable service discovery")
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    startup_delay: int = Field(default=5, description="Delay between service startups")
    
    class Config:
        arbitrary_types_allowed = True
    
    @classmethod
    def create_default(cls, project_root: str, environment: IBEnvironment = IBEnvironment.DEVELOPMENT) -> 'IBOrchestrationConfig':
        """Create a default orchestration configuration."""
        
        # Generate instance-specific base values using path hash
        instance_hash = cls._generate_instance_hash(project_root)
        base_client_id = 100 + (instance_hash % 900)  # Range: 100-999
        base_port = 8000 + (instance_hash % 1000)     # Range: 8000-8999
        
        # Create base configuration with proper nested config initialization
        base_config = IBBaseConfig(
            environment=environment,
            service_name="orchestration",
            project_root=project_root,
            instance_id=f"{instance_hash:08x}",
            connection=IBConnectionConfig(
                host="localhost",
                ports=[4002],
                client_id=base_client_id
            ),
            server=IBServerConfig(
                host="0.0.0.0",
                port=base_port
            ),
            storage=IBStorageConfig()
        )
        
        # Define services
        services = {
            "ib-stream": ServiceConfig(
                name=ServiceType.STREAM,
                enabled=True,
                port_offset=0,        # Uses base_port
                client_id_offset=0,   # Uses base_client_id
            ),
            "ib-contract": ServiceConfig(
                name=ServiceType.CONTRACT,
                enabled=True,
                port_offset=10,       # base_port + 10
                client_id_offset=1,   # base_client_id + 1
            ),
        }
        
        return cls(
            environment=environment,
            project_root=project_root,
            base_config=base_config,
            services=services,
        )
    
    @staticmethod
    def _generate_instance_hash(project_root: str) -> int:
        """Generate a hash from the project root path for instance isolation."""
        normalized_path = str(Path(project_root).absolute())
        hash_object = hashlib.md5(normalized_path.encode())
        return int(hash_object.hexdigest()[:8], 16)
    
    def get_service_config(self, service_name: str) -> Optional[IBBaseConfig]:
        """Get complete configuration for a specific service."""
        if service_name not in self.services:
            return None
            
        service = self.services[service_name]
        if not service.enabled:
            return None
        
        # Create a copy of base config
        config_dict = self.base_config.dict()
        
        # Apply service-specific modifications
        config_dict['service_name'] = service_name
        config_dict['connection']['client_id'] += service.client_id_offset
        config_dict['server']['port'] += service.port_offset
        
        # Apply any service overrides
        for key, value in service.config_overrides.items():
            self._set_nested_value(config_dict, key, value)
        
        return IBBaseConfig(**config_dict)
    
    def _set_nested_value(self, config_dict: dict, key: str, value: Any):
        """Set a nested value in the config dictionary using dot notation."""
        keys = key.split('.')
        current = config_dict
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def get_all_service_configs(self) -> Dict[str, IBBaseConfig]:
        """Get configurations for all enabled services."""
        configs = {}
        for service_name in self.services:
            config = self.get_service_config(service_name)
            if config:
                configs[service_name] = config
        return configs
    
    def get_ports_in_use(self) -> List[int]:
        """Get all ports that will be used by services."""
        ports = []
        for service_name in self.services:
            config = self.get_service_config(service_name)
            if config:
                service = self.services[service_name]
                for replica in range(service.replicas):
                    ports.append(config.server.port + replica)
        return sorted(ports)
    
    def get_client_ids_in_use(self) -> List[int]:
        """Get all client IDs that will be used by services."""
        client_ids = []
        for service_name in self.services:
            config = self.get_service_config(service_name)
            if config:
                service = self.services[service_name]
                for replica in range(service.replicas):
                    client_ids.append(config.connection.client_id + replica)
        return sorted(client_ids)
    
    def validate_no_conflicts(self) -> bool:
        """Validate that there are no port or client ID conflicts."""
        ports = self.get_ports_in_use()
        client_ids = self.get_client_ids_in_use()
        
        # Check for duplicate ports
        if len(ports) != len(set(ports)):
            raise ValueError(f"Port conflicts detected: {ports}")
        
        # Check for duplicate client IDs
        if len(client_ids) != len(set(client_ids)):
            raise ValueError(f"Client ID conflicts detected: {client_ids}")
        
        return True
    
    def to_supervisor_config(self) -> str:
        """Generate supervisor configuration for all services."""
        lines = [
            "[unix_http_server]",
            f"file={self.project_root}/supervisor.sock",
            "",
            "[supervisord]",
            f"logfile={self.project_root}/logs/supervisord.log",
            f"pidfile={self.project_root}/supervisord.pid",
            f"childlogdir={self.project_root}/logs",
            "nodaemon=false",
            "",
            "[rpcinterface:supervisor]",
            "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface",
            "",
            "[supervisorctl]",
            f"serverurl=unix://{self.project_root}/supervisor.sock",
            "",
        ]
        
        for service_name, service in self.services.items():
            if not service.enabled:
                continue
                
            config = self.get_service_config(service_name)
            if not config:
                continue
            
            env_vars = config.to_env_dict()
            env_string = ",".join([f"{k}={v}" for k, v in env_vars.items()])
            
            # Determine command and directory based on service type
            if service.name == ServiceType.STREAM:
                command = f"{self.project_root}/.venv/bin/uvicorn ib_stream.api_server:app --host {config.server.host} --port {config.server.port}"
                directory = f"{self.project_root}/ib-stream"
            elif service.name == ServiceType.CONTRACT:
                command = f"{self.project_root}/.venv/bin/uvicorn api_server:app --host {config.server.host} --port {config.server.port}"
                directory = f"{self.project_root}/ib-contract"
            else:
                continue  # Skip unknown service types
            
            program_name = f"{service_name}-{self.environment.value}"
            
            lines.extend([
                f"[program:{program_name}]",
                f"command={command}",
                f"directory={directory}",
                f"environment={env_string}",
                "autostart=true",
                "autorestart=true",
                "startretries=3",
                f"user={self._get_current_user()}",
                f"stdout_logfile={self.project_root}/logs/{program_name}-stdout.log",
                f"stderr_logfile={self.project_root}/logs/{program_name}-stderr.log",
                "stdout_logfile_maxbytes=10MB",
                "stderr_logfile_maxbytes=10MB",
                "stdout_logfile_backups=5",
                "stderr_logfile_backups=5",
                "",
            ])
        
        return "\n".join(lines)
    
    def _get_current_user(self) -> str:
        """Get the current user for supervisor configuration."""
        import os
        return os.getenv("USER", "nobody")


def load_orchestration_config(
    project_root: str,
    environment: IBEnvironment = IBEnvironment.DEVELOPMENT,
    config_file: Optional[str] = None
) -> IBOrchestrationConfig:
    """
    Load orchestration configuration from file or create default.
    
    Args:
        project_root: Root directory of the project
        environment: Target environment
        config_file: Optional path to configuration file
        
    Returns:
        Loaded orchestration configuration
    """
    if config_file and Path(config_file).exists():
        # TODO: Implement YAML/TOML loading
        # For now, create default
        pass
    
    # Create default configuration
    return IBOrchestrationConfig.create_default(project_root, environment)