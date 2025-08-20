"""
Stream Health Service

Integrates trading hours data with background stream health monitoring.
Provides market status determination and contract-specific health assessment.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, List
from dataclasses import dataclass

from ib_util.trading_hours import (
    check_contract_market_status, get_contract_trading_schedule,
    MarketStatusResult, ValidationError, validate_contract_id
)
from ib_util.trading_hours_service import MarketStatusService, CachedContractRepository
from ib_util.contract_cache import ContractIndex

from ..models.background_health import (
    StreamHealthStatus, MarketStatus, ContractTradingHours, 
    ContractHealthStatus, DataFreshnessCheck, StreamInfo
)

logger = logging.getLogger(__name__)


class StreamHealthService:
    """
    Service for assessing background stream health with trading hours awareness
    """
    
    def __init__(self, contract_index: Optional[ContractIndex] = None):
        self.contract_index = contract_index
        self.trading_hours_cache: Dict[int, ContractTradingHours] = {}
        self.contract_details_cache: Dict[int, Dict[str, Any]] = {}
        
        # Initialize market status service if we have contract index
        self.market_status_service = None
        if contract_index:
            try:
                contract_repo = CachedContractRepository(contract_index)
                self.market_status_service = MarketStatusService(contract_repo)
                logger.info("StreamHealthService initialized with market status service")
            except Exception as e:
                logger.warning("Could not initialize market status service: %s", e)
    
    async def get_contract_market_status(self, contract_id: int) -> MarketStatus:
        """
        Determine current market status for a contract
        
        Args:
            contract_id: IB contract ID
            
        Returns:
            MarketStatus enum value
        """
        try:
            validate_contract_id(contract_id)
            
            # Try to get market status using ib-util market status service
            if self.market_status_service:
                try:
                    market_result = await self._get_market_status_from_service(contract_id)
                    if market_result:
                        return self._convert_market_status(market_result)
                except Exception as e:
                    logger.debug("Market status service check failed for contract %d: %s", contract_id, e)
            
            # Fallback to direct API call
            try:
                market_result = check_contract_market_status(contract_id)
                return self._convert_market_status(market_result)
            except Exception as e:
                logger.warning("Could not determine market status for contract %d: %s", contract_id, e)
                return MarketStatus.UNKNOWN
                
        except ValidationError as e:
            logger.error("Invalid contract ID %d: %s", contract_id, e)
            return MarketStatus.UNKNOWN
        except Exception as e:
            logger.error("Error getting market status for contract %d: %s", contract_id, e)
            return MarketStatus.UNKNOWN
    
    async def _get_market_status_from_service(self, contract_id: int) -> Optional[MarketStatusResult]:
        """Get market status using the market status service"""
        if not self.market_status_service:
            return None
            
        try:
            return await self.market_status_service.check_contract_market_status(contract_id)
        except Exception as e:
            logger.debug("Market status service error for contract %d: %s", contract_id, e)
            return None
    
    def _convert_market_status(self, market_result: MarketStatusResult) -> MarketStatus:
        """Convert MarketStatusResult to our MarketStatus enum"""
        if not market_result:
            return MarketStatus.UNKNOWN
            
        if market_result.is_open:
            return MarketStatus.OPEN
        elif market_result.in_extended_hours:
            # Determine if pre-market or after-hours based on time
            # This is a simplified approach - could be enhanced with more detailed logic
            now = datetime.now(timezone.utc)
            if now.hour < 12:  # Rough heuristic for pre-market (Eastern timezone aware)
                return MarketStatus.PRE_MARKET
            else:
                return MarketStatus.AFTER_HOURS
        else:
            return MarketStatus.CLOSED
    
    async def get_contract_trading_hours(self, contract_id: int, 
                                       force_refresh: bool = False) -> Optional[ContractTradingHours]:
        """
        Get trading hours information for a contract with caching
        
        Args:
            contract_id: IB contract ID
            force_refresh: Force refresh of cached data
            
        Returns:
            ContractTradingHours or None if not available
        """
        try:
            validate_contract_id(contract_id)
            
            # Check cache first (unless force refresh)
            if not force_refresh and contract_id in self.trading_hours_cache:
                cached_hours = self.trading_hours_cache[contract_id]
                if not cached_hours.is_expired():
                    return cached_hours
                else:
                    # Remove expired entry
                    del self.trading_hours_cache[contract_id]
                    logger.debug("Removed expired trading hours cache for contract %d", contract_id)
            
            # Fetch fresh trading hours data
            try:
                schedule = get_contract_trading_schedule(contract_id)
                if schedule:
                    trading_hours = ContractTradingHours(
                        timezone=getattr(schedule, 'timezone', 'UTC'),
                        regular_hours=getattr(schedule, 'regular_hours', 'Unknown'),
                        extended_hours=getattr(schedule, 'extended_hours', None)
                    )
                    
                    # Cache the result
                    self.trading_hours_cache[contract_id] = trading_hours
                    logger.debug("Cached trading hours for contract %d", contract_id)
                    
                    return trading_hours
                    
            except Exception as e:
                logger.warning("Could not fetch trading schedule for contract %d: %s", contract_id, e)
            
            return None
            
        except ValidationError as e:
            logger.error("Invalid contract ID %d: %s", contract_id, e)
            return None
        except Exception as e:
            logger.error("Error getting trading hours for contract %d: %s", contract_id, e)
            return None
    
    async def assess_contract_health(self, 
                                   contract_id: int,
                                   symbol: str,
                                   expected_streams: List[str],
                                   active_streams: Dict[str, int],
                                   stream_handlers: Dict[int, Any],
                                   last_data_timestamps: Dict[int, datetime],
                                   staleness_threshold_minutes: int = 15,
                                   buffer_hours: int = 1) -> ContractHealthStatus:
        """
        Perform comprehensive health assessment for a contract
        
        Args:
            contract_id: IB contract ID
            symbol: Contract symbol (e.g., 'MNQ')
            expected_streams: List of expected tick types
            active_streams: Dict of tick_type -> request_id for active streams
            stream_handlers: Dict of request_id -> handler objects
            last_data_timestamps: Dict of contract_id -> last_data_time
            staleness_threshold_minutes: Minutes before data is considered stale
            buffer_hours: Buffer hours configuration for this contract
            
        Returns:
            ContractHealthStatus with complete assessment
        """
        try:
            # Get market status and trading hours
            market_status = await self.get_contract_market_status(contract_id)
            trading_hours = await self.get_contract_trading_hours(contract_id)
            
            # Assess data staleness
            last_data_time = last_data_timestamps.get(contract_id)
            data_staleness = DataFreshnessCheck(
                last_tick_timestamp=last_data_time,
                threshold_minutes=staleness_threshold_minutes
            )
            
            # Build stream info
            streams = {}
            for tick_type in expected_streams:
                request_id = active_streams.get(tick_type)
                is_active = request_id is not None
                
                # Get stream-specific last tick time if available
                stream_last_tick = last_data_time  # Simplified - could be per-stream
                
                streams[tick_type] = StreamInfo(
                    tick_type=tick_type,
                    is_active=is_active,
                    request_id=request_id,
                    last_tick_timestamp=stream_last_tick
                )
            
            # Create health status
            health_status = ContractHealthStatus(
                contract_id=contract_id,
                symbol=symbol,
                status=StreamHealthStatus.UNKNOWN,  # Will be calculated
                market_status=market_status,
                trading_hours=trading_hours,
                data_staleness=data_staleness,
                streams=streams,
                total_streams_expected=len(expected_streams),
                total_streams_active=len(active_streams),
                buffer_hours=buffer_hours
            )
            
            # Calculate overall status based on conditions
            health_status.status = health_status.calculate_overall_status(staleness_threshold_minutes)
            
            logger.debug("Health assessment for contract %d (%s): %s", 
                        contract_id, symbol, health_status.status.value)
            
            return health_status
            
        except Exception as e:
            logger.error("Error assessing health for contract %d: %s", contract_id, e)
            
            # Return minimal health status with error
            return ContractHealthStatus(
                contract_id=contract_id,
                symbol=symbol,
                status=StreamHealthStatus.UNKNOWN,
                market_status=MarketStatus.UNKNOWN,
                connection_issues=[f"Health assessment error: {str(e)}"]
            )
    
    def is_data_expected_now(self, market_status: MarketStatus, 
                           trading_hours: Optional[ContractTradingHours] = None) -> bool:
        """
        Determine if data flow is expected based on current market conditions
        
        Args:
            market_status: Current market status
            trading_hours: Trading hours information (optional)
            
        Returns:
            True if data is expected, False otherwise
        """
        if market_status == MarketStatus.OPEN:
            return True
        elif market_status in [MarketStatus.PRE_MARKET, MarketStatus.AFTER_HOURS]:
            # Some data expected in extended hours, but less frequent
            return True
        elif market_status == MarketStatus.CLOSED:
            return False
        else:
            # Unknown status - assume data might be expected to avoid false alarms
            return True
    
    def get_staleness_threshold_for_market(self, market_status: MarketStatus,
                                         base_threshold_minutes: int = 15) -> int:
        """
        Get appropriate staleness threshold based on market conditions
        
        Args:
            market_status: Current market status
            base_threshold_minutes: Base threshold for regular hours
            
        Returns:
            Appropriate threshold in minutes
        """
        if market_status == MarketStatus.OPEN:
            return base_threshold_minutes
        elif market_status in [MarketStatus.PRE_MARKET, MarketStatus.AFTER_HOURS]:
            # More lenient during extended hours
            return base_threshold_minutes * 3
        elif market_status == MarketStatus.CLOSED:
            # Very lenient when closed - data not expected
            return base_threshold_minutes * 10
        else:
            return base_threshold_minutes
    
    def clear_cache(self):
        """Clear all cached data"""
        self.trading_hours_cache.clear()
        self.contract_details_cache.clear()
        logger.info("StreamHealthService cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "trading_hours_cached": len(self.trading_hours_cache),
            "contract_details_cached": len(self.contract_details_cache)
        }