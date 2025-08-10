"""
Trading Hours Service - SOLID Principles Implementation
Separates trading hours functionality into dedicated service classes
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from abc import ABC, abstractmethod

from .trading_hours import (
    TradingHoursParser, MarketStatusResult, ValidationError,
    validate_contract_id, check_contract_market_status, get_contract_trading_schedule
)
from .contract_cache import ContractIndex, ContractCacheEntry

logger = logging.getLogger(__name__)


class ContractRepository(ABC):
    """Abstract repository interface for contract data access"""
    
    @abstractmethod
    def find_by_contract_id(self, contract_id: int) -> Optional[Dict]:
        """Find contract by ID"""
        pass


class CachedContractRepository(ContractRepository):
    """Cached implementation of contract repository"""
    
    def __init__(self, contract_index: ContractIndex, cache_manager=None):
        self.contract_index = contract_index
        self.cache_manager = cache_manager
        self.logger = logging.getLogger(__name__)
    
    def find_by_contract_id(self, contract_id: int) -> Optional[Dict]:
        """Find contract using fast index lookup"""
        try:
            # Use the contract index for O(1) lookup
            cache_entry = self.contract_index.find_by_contract_id(contract_id)
            
            if cache_entry and not cache_entry.is_expired(ttl_hours=24):
                return cache_entry.contract_data
            
            # Remove expired entry if found
            if cache_entry:
                self.contract_index.remove_contract(contract_id)
                self.logger.debug(f"Removed expired cache entry for contract {contract_id}")
            
            # Attempt index rebuild if cache manager available
            if self.cache_manager and not hasattr(self, '_index_rebuilt_recently'):
                self.contract_index.rebuild_from_cache_manager(self.cache_manager)
                self._index_rebuilt_recently = True
                
                # Try again after rebuild
                cache_entry = self.contract_index.find_by_contract_id(contract_id)
                if cache_entry and not cache_entry.is_expired(ttl_hours=24):
                    return cache_entry.contract_data
            
            return None
            
        except Exception as e:
            self.logger.error("Error in contract repository lookup for ID %d: %s", contract_id, e)
            return None


class MarketStatusService:
    """Service for determining market status and trading hours"""
    
    def __init__(self, contract_repository: ContractRepository):
        self.contract_repository = contract_repository
        self.parser = TradingHoursParser()
        self.logger = logging.getLogger(__name__)
    
    def get_market_status(self, contract_id: int, check_time: Optional[datetime] = None) -> Optional[MarketStatusResult]:
        """
        Get market status for a contract
        
        Args:
            contract_id: Contract ID to check
            check_time: Time to check (defaults to now)
            
        Returns:
            MarketStatusResult or None if contract not found
            
        Raises:
            ValidationError: If contract ID is invalid
        """
        # Validate input
        validated_contract_id = validate_contract_id(contract_id)
        
        # Retrieve contract data
        contract_data = self.contract_repository.find_by_contract_id(validated_contract_id)
        if not contract_data:
            self.logger.warning(f"Contract {validated_contract_id} not found in repository")
            return None
        
        # Check market status using cached contract data
        try:
            return check_contract_market_status(contract_data, check_time)
        except Exception as e:
            self.logger.error("Failed to check market status for contract %d: %s", validated_contract_id, e)
            raise
    
    def get_trading_hours_info(self, contract_id: int) -> Optional[Dict]:
        """
        Get detailed trading hours information for a contract
        
        Args:
            contract_id: Contract ID to lookup
            
        Returns:
            Trading hours information dictionary or None if not found
        """
        # Validate input
        validated_contract_id = validate_contract_id(contract_id)
        
        # Retrieve contract data
        contract_data = self.contract_repository.find_by_contract_id(validated_contract_id)
        if not contract_data:
            return None
        
        return {
            "contract_id": validated_contract_id,
            "contract_info": {
                "symbol": contract_data.get("symbol"),
                "sec_type": contract_data.get("sec_type"),
                "exchange": contract_data.get("exchange"),
                "currency": contract_data.get("currency"),
                "market_name": contract_data.get("market_name")
            },
            "trading_hours_info": {
                "time_zone_id": contract_data.get("time_zone_id"),
                "trading_hours": contract_data.get("trading_hours"),
                "liquid_hours": contract_data.get("liquid_hours"),
                "retrieved_at": contract_data.get("retrieved_at")
            }
        }
    
    def get_trading_schedule(self, contract_id: int, days_ahead: int = 7) -> Optional[Dict]:
        """
        Get upcoming trading schedule for a contract
        
        Args:
            contract_id: Contract ID to lookup
            days_ahead: Number of days to look ahead (1-30)
            
        Returns:
            Trading schedule dictionary or None if not found
            
        Raises:
            ValidationError: If parameters are invalid
        """
        # Validate inputs
        validated_contract_id = validate_contract_id(contract_id)
        
        if not isinstance(days_ahead, int) or not (1 <= days_ahead <= 30):
            raise ValidationError("Days parameter must be an integer between 1 and 30")
        
        # Retrieve contract data
        contract_data = self.contract_repository.find_by_contract_id(validated_contract_id)
        if not contract_data:
            return None
        
        try:
            schedule = get_contract_trading_schedule(contract_data, days_ahead=days_ahead)
            
            return {
                "contract_id": validated_contract_id,
                "contract_info": {
                    "symbol": contract_data.get("symbol"),
                    "sec_type": contract_data.get("sec_type"),
                    "exchange": contract_data.get("exchange"),
                    "currency": contract_data.get("currency")
                },
                "days_requested": days_ahead,
                "schedule": schedule
            }
        except Exception as e:
            self.logger.error("Failed to get trading schedule for contract %d: %s", validated_contract_id, e)
            raise


class TradingHoursServiceFactory:
    """Factory for creating trading hours service instances"""
    
    @staticmethod
    def create_service(contract_index: ContractIndex, cache_manager=None) -> MarketStatusService:
        """
        Create a market status service with cached contract repository
        
        Args:
            contract_index: Contract index for fast lookups
            cache_manager: Optional cache manager for index rebuilding
            
        Returns:
            Configured MarketStatusService instance
        """
        repository = CachedContractRepository(contract_index, cache_manager)
        return MarketStatusService(repository)


# Circuit Breaker Pattern Implementation
class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """Simple circuit breaker for external service calls"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half-open
        self.logger = logging.getLogger(__name__)
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == 'open':
            if self._should_attempt_reset():
                self.state = 'half-open'
                self.logger.info("Circuit breaker half-open, attempting call")
            else:
                raise CircuitBreakerError("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return False
        return (datetime.now() - self.last_failure_time).seconds >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        self.state = 'closed'
        if self.state == 'half-open':
            self.logger.info("Circuit breaker closed after successful call")
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'open'
            self.logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class ResilientMarketStatusService(MarketStatusService):
    """Market status service with circuit breaker protection"""
    
    def __init__(self, contract_repository: ContractRepository, 
                 circuit_breaker: Optional[CircuitBreaker] = None):
        super().__init__(contract_repository)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
    
    def get_market_status(self, contract_id: int, check_time: Optional[datetime] = None) -> Optional[MarketStatusResult]:
        """Get market status with circuit breaker protection"""
        try:
            return self.circuit_breaker.call(
                super().get_market_status, 
                contract_id, 
                check_time
            )
        except CircuitBreakerError:
            self.logger.warning(f"Circuit breaker prevented market status check for contract {contract_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get market status for contract {contract_id}: {e}")
            return None
    
    def get_trading_hours_info(self, contract_id: int) -> Optional[Dict]:
        """Get trading hours info with circuit breaker protection"""
        try:
            return self.circuit_breaker.call(
                super().get_trading_hours_info, 
                contract_id
            )
        except CircuitBreakerError:
            self.logger.warning(f"Circuit breaker prevented trading hours lookup for contract {contract_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get trading hours for contract {contract_id}: {e}")
            return None
    
    def get_trading_schedule(self, contract_id: int, days_ahead: int = 7) -> Optional[Dict]:
        """Get trading schedule with circuit breaker protection"""
        try:
            return self.circuit_breaker.call(
                super().get_trading_schedule, 
                contract_id, 
                days_ahead
            )
        except CircuitBreakerError:
            self.logger.warning(f"Circuit breaker prevented trading schedule lookup for contract {contract_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get trading schedule for contract {contract_id}: {e}")
            return None