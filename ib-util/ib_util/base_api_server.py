"""
Base API Server class for IB services

Provides common FastAPI server functionality including standardized setup,
logging configuration, health checks, and lifecycle management.
"""

import logging
import os
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI

from .config_loader import load_environment_config
from .logging_config import configure_service_logging, log_environment_info


class BaseAPIServer(ABC):
    """
    Base class for IB API servers providing common functionality
    
    This class implements the template method pattern, allowing subclasses
    to customize specific behavior while maintaining consistent server setup.
    """
    
    def __init__(
        self,
        service_name: str,
        service_type: str = "stream",
        title: Optional[str] = None,
        description: Optional[str] = None,
        version: str = "1.0.0",
        verbose_logging: bool = True
    ):
        """
        Initialize base API server
        
        Args:
            service_name: Name of the service (e.g., "ib-stream", "ib-contract")
            service_type: Service type for configuration ("stream" or "contracts")
            title: API title for documentation
            description: API description for documentation
            version: API version
            verbose_logging: Enable verbose logging
        """
        self.service_name = service_name
        self.service_type = service_type
        self.version = version
        
        # Configure logging
        self.logger = configure_service_logging(service_name, verbose=verbose_logging)
        
        # Load configuration
        self.config = load_environment_config(service_type)
        
        # Set defaults if not provided
        if title is None:
            title = f"{service_name.upper()} API Server"
        if description is None:
            description = f"API server for {service_name}"
            
        # Create FastAPI app with lifespan
        self.app = FastAPI(
            title=title,
            description=description,
            version=version,
            lifespan=self._create_lifespan()
        )
        
        # Setup common endpoints
        self._setup_common_endpoints()
        
        # Allow subclasses to setup specific endpoints
        self.setup_endpoints()
    
    def _create_lifespan(self):
        """Create lifespan context manager for FastAPI"""
        @asynccontextmanager
        async def lifespan(_: FastAPI):
            # Startup
            self.logger.info("Starting %s API server...", self.service_name)
            log_environment_info(self.logger, self.service_name)
            
            try:
                await self.startup()
                self.logger.info("%s API server started successfully", self.service_name)
            except Exception as e:
                self.logger.error("Failed to start %s API server: %s", self.service_name, e)
                raise
            
            yield
            
            # Shutdown
            self.logger.info("Shutting down %s API server...", self.service_name)
            try:
                await self.shutdown()
                self.logger.info("%s API server shutdown complete", self.service_name)
            except Exception as e:
                self.logger.error("Error during %s shutdown: %s", self.service_name, e)
        
        return lifespan
    
    def _setup_common_endpoints(self):
        """Setup common endpoints that all services should have"""
        
        @self.app.get("/")
        async def root():
            """Root endpoint with API information"""
            info = self.get_api_info()
            return {
                "message": info.get("title", f"{self.service_name} API"),
                "version": self.version,
                "service": self.service_name,
                **info
            }
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return await self.get_health_status()
    
    @abstractmethod
    def setup_endpoints(self):
        """Setup service-specific endpoints - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    async def startup(self):
        """Service-specific startup logic - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    async def shutdown(self):
        """Service-specific shutdown logic - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    def get_api_info(self) -> Dict[str, Any]:
        """Get service-specific API information - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    async def get_health_status(self) -> Dict[str, Any]:
        """Get service-specific health status - must be implemented by subclasses"""
        pass
    
    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration for uvicorn"""
        port_env_var = f"{self.service_name.upper().replace('-', '_')}_PORT"
        default_port = 8000 if self.service_type == "stream" else 8010
        
        return {
            "host": os.getenv("HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", os.getenv(port_env_var, str(default_port)))),
            "log_level": "info",
            "reload": os.getenv("RELOAD", "false").lower() == "true"
        }
    
    def run(self, **kwargs):
        """Run the server with uvicorn"""
        server_config = self.get_server_config()
        server_config.update(kwargs)
        
        self.logger.info(
            "Starting %s on %s:%d", 
            self.service_name, 
            server_config["host"], 
            server_config["port"]
        )
        
        # Determine module path for reload
        module_path = f"{self.service_name.replace('-', '_')}.api_server:app"
        
        uvicorn.run(
            module_path if server_config["reload"] else self.app,
            **server_config
        )


def create_standardized_health_response(
    service_name: str,
    status: str,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standardized health check response
    
    Args:
        service_name: Name of the service
        status: Health status ("healthy", "unhealthy", "degraded")
        details: Additional health details
        
    Returns:
        Standardized health response dictionary
    """
    from .response_formatting import create_health_check_response
    return create_health_check_response(service_name, status, details or {})


def create_standardized_error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standardized error response
    
    Args:
        message: Error message
        error_code: Optional error code
        details: Additional error details
        
    Returns:
        Standardized error response dictionary
    """
    from datetime import datetime
    
    response = {
        "error": True,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    
    if error_code:
        response["error_code"] = error_code
    if details:
        response["details"] = details
        
    return response