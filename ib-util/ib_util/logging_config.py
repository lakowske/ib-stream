"""
Standardized logging configuration for IB services

This module provides consistent logging setup across ib-stream, ib-contract,
and other IB API services with proper TWS API noise suppression.
"""

import logging
import os
from typing import Optional


def configure_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    suppress_ibapi: bool = True,
    verbose: bool = False
) -> None:
    """
    Configure standardized logging for IB services
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string, uses default if None
        suppress_ibapi: Whether to suppress noisy IB API logging
        verbose: If True, shows more detailed logging with module names and line numbers
    """
    # Determine log level
    if isinstance(level, str):
        log_level = getattr(logging, level.upper(), logging.INFO)
    else:
        log_level = level
    
    # Default format strings
    if format_string is None:
        if verbose:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        else:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure basic logging
    logging.basicConfig(
        level=log_level,
        format=format_string,
        force=True  # Override any existing configuration
    )
    
    # Suppress noisy IB API logging if requested
    if suppress_ibapi:
        suppress_ibapi_logging()


def suppress_ibapi_logging() -> None:
    """Suppress noisy IB API logging that clutters output"""
    # Suppress ibapi module logging
    logging.getLogger("ibapi").setLevel(logging.CRITICAL)
    
    # Also suppress common noisy loggers
    noisy_loggers = [
        "ibapi.client",
        "ibapi.wrapper", 
        "ibapi.reader",
        "ibapi.comm",
        "urllib3",
        "requests"
    ]
    
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def configure_service_logging(service_name: str, verbose: bool = False) -> logging.Logger:
    """
    Configure logging for a specific IB service with consistent defaults
    
    Args:
        service_name: Name of the service (e.g., "ib-stream", "ib-contract")
        verbose: Whether to use verbose logging
        
    Returns:
        Logger instance for the service
    """
    # Load log level from environment with sensible defaults
    if service_name == "ib-stream":
        default_level = os.getenv("IB_STREAM_LOG_LEVEL", "INFO")
    elif service_name == "ib-contract":
        default_level = os.getenv("IB_CONTRACTS_LOG_LEVEL", "INFO") 
    else:
        default_level = os.getenv("IB_LOG_LEVEL", "INFO")
    
    # Configure logging
    configure_logging(
        level=default_level,
        verbose=verbose,
        suppress_ibapi=True
    )
    
    # Return service-specific logger
    return logging.getLogger(service_name)


def configure_cli_logging(verbose: bool = False) -> None:
    """
    Configure logging for CLI tools with appropriate noise suppression
    
    Args:
        verbose: If True, show INFO level; if False, suppress most output
    """
    if verbose:
        configure_logging(
            level="INFO",
            verbose=True,
            suppress_ibapi=True
        )
    else:
        # Suppress almost everything for CLI tools unless it's critical
        configure_logging(
            level="CRITICAL",
            format_string="%(asctime)s - %(levelname)s - %(message)s",
            suppress_ibapi=True
        )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with consistent naming
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_environment_info(logger: logging.Logger, service_name: str) -> None:
    """
    Log environment configuration information for debugging
    
    Args:
        logger: Logger instance to use
        service_name: Name of the service
    """
    logger.info("=== %s Environment Configuration ===", service_name)
    
    # Common IB environment variables
    env_vars = [
        "IB_STREAM_HOST",
        "IB_STREAM_PORTS", 
        "IB_STREAM_CLIENT_ID",
        "IB_CONTRACTS_CLIENT_ID",
        "IB_STREAM_ENV",
        "IB_STREAM_LOG_LEVEL",
        "IB_CONTRACTS_LOG_LEVEL"
    ]
    
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if "PASSWORD" in var or "SECRET" in var or "KEY" in var:
                logger.info("  %s: ***MASKED***", var)
            else:
                logger.info("  %s: %s", var, value)
        else:
            logger.debug("  %s: not set", var)
    
    logger.info("  Current working directory: %s", os.getcwd())
    logger.info("=== End Environment Configuration ===")


# Convenience functions for different log levels
def setup_debug_logging() -> None:
    """Setup debug-level logging for development"""
    configure_logging(level="DEBUG", verbose=True, suppress_ibapi=False)


def setup_production_logging() -> None:
    """Setup production-appropriate logging"""
    configure_logging(level="INFO", verbose=False, suppress_ibapi=True)


def setup_quiet_logging() -> None:
    """Setup minimal logging for CLI tools"""
    configure_cli_logging(verbose=False)