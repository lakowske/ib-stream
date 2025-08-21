"""
Health Monitor Component - Category Theory Compliant

Handles only health monitoring and staleness detection:
- Single responsibility: health monitoring only
- Pure functions for health calculations
- Composition via well-defined interfaces
- Identity element: no-op for unchanged health state
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from ..models.background_health import (
    BackgroundStreamHealth, ContractHealthStatus, StreamHealthStatus
)
from ..services.stream_health_service import StreamHealthService
from ..config import TrackedContract

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Pure health monitoring component.
    
    Categorical Properties:
    - Identity: health assessment returns same result for unchanged state
    - Composition: health metrics compose via aggregation functions
    - Single responsibility: only monitors and reports health
    """
    
    def __init__(self, tracked_contracts: Dict[int, TrackedContract], 
                 staleness_threshold_minutes: int = 15):
        self.tracked_contracts = tracked_contracts
        self.staleness_threshold = timedelta(minutes=staleness_threshold_minutes)
        
        # Data tracking (immutable timestamps)
        self.last_data_timestamps: Dict[int, datetime] = {}
        
        # Health service for market status
        self.health_service = StreamHealthService()
    
    def update_data_timestamp(self, contract_id: int, timestamp: Optional[datetime] = None) -> None:
        """Update last data received timestamp for contract"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.last_data_timestamps[contract_id] = timestamp
        logger.debug("Updated data timestamp for contract %d", contract_id)
    
    def set_staleness_threshold(self, minutes: int) -> None:
        """Update staleness threshold (pure function when same value)"""
        new_threshold = timedelta(minutes=minutes)
        if self.staleness_threshold == new_threshold:
            return  # Identity property
        
        self.staleness_threshold = new_threshold
        logger.info("Updated staleness threshold to %d minutes", minutes)
    
    async def assess_contract_health(self, contract_id: int, 
                                   is_streaming: bool) -> Optional[ContractHealthStatus]:
        """
        Assess health for a specific contract (pure function given inputs).
        
        Returns None if contract is not tracked.
        """
        contract = self.tracked_contracts.get(contract_id)
        if not contract:
            return None
        
        try:
            # Get last data timestamp
            last_data_time = self.last_data_timestamps.get(contract_id)
            
            # Assess health using the health service
            health_status = await self.health_service.assess_contract_health(
                contract_id=contract_id,
                last_data_time=last_data_time,
                staleness_threshold_minutes=int(self.staleness_threshold.total_seconds() / 60),
                is_streaming=is_streaming
            )
            
            return health_status
            
        except Exception as e:
            logger.error("Error assessing health for contract %d: %s", contract_id, e)
            # Return unhealthy status on error
            return ContractHealthStatus(
                contract_id=contract_id,
                status=StreamHealthStatus.UNHEALTHY,
                last_data_time=last_data_time,
                staleness_minutes=9999,  # Very high staleness to indicate error
                market_status="UNKNOWN",
                is_trading_hours=False,
                next_trading_session=None,
                error_message=str(e)
            )
    
    async def get_comprehensive_health(self, active_contracts: Set[int]) -> BackgroundStreamHealth:
        """
        Get comprehensive health for all tracked contracts (pure function given inputs).
        """
        contract_health_list = []
        
        # Assess health for each tracked contract
        for contract_id in self.tracked_contracts.keys():
            is_streaming = contract_id in active_contracts
            
            contract_health = await self.assess_contract_health(contract_id, is_streaming)
            if contract_health:
                contract_health_list.append(contract_health)
        
        # Calculate summary statistics (pure functions)
        total_contracts = len(contract_health_list)
        healthy_count = sum(1 for h in contract_health_list if h.status == StreamHealthStatus.HEALTHY)
        degraded_count = sum(1 for h in contract_health_list if h.status == StreamHealthStatus.DEGRADED)
        unhealthy_count = sum(1 for h in contract_health_list if h.status == StreamHealthStatus.UNHEALTHY)
        off_hours_count = sum(1 for h in contract_health_list if h.status == StreamHealthStatus.OFF_HOURS)
        
        return BackgroundStreamHealth(
            total_contracts=total_contracts,
            healthy_contracts=healthy_count,
            degraded_contracts=degraded_count,
            unhealthy_contracts=unhealthy_count,
            off_hours_contracts=off_hours_count,
            contract_health=contract_health_list,
            staleness_threshold_minutes=int(self.staleness_threshold.total_seconds() / 60),
            assessment_time=datetime.now()
        )
    
    def get_health_summary(self, active_contracts: Set[int]) -> Dict[str, any]:
        """
        Get health summary (pure function given inputs).
        """
        current_time = datetime.now()
        
        # Calculate staleness for each contract
        stale_contracts = []
        active_contract_count = 0
        
        for contract_id in self.tracked_contracts.keys():
            if contract_id in active_contracts:
                active_contract_count += 1
                
                last_data = self.last_data_timestamps.get(contract_id)
                if last_data:
                    staleness = current_time - last_data
                    if staleness > self.staleness_threshold:
                        stale_contracts.append(contract_id)
        
        return {
            "total_contracts": len(self.tracked_contracts),
            "active_contracts": active_contract_count,
            "stale_contracts": len(stale_contracts),
            "healthy_contracts": active_contract_count - len(stale_contracts),
            "staleness_threshold_minutes": int(self.staleness_threshold.total_seconds() / 60),
            "last_updated": current_time.isoformat()
        }
    
    def is_contract_stale(self, contract_id: int) -> bool:
        """
        Check if contract data is stale (pure function).
        """
        last_data = self.last_data_timestamps.get(contract_id)
        if not last_data:
            return True  # No data received yet
        
        staleness = datetime.now() - last_data
        return staleness > self.staleness_threshold
    
    def get_contract_staleness_minutes(self, contract_id: int) -> Optional[float]:
        """
        Get staleness in minutes for contract (pure function).
        Returns None if no data received yet.
        """
        last_data = self.last_data_timestamps.get(contract_id)
        if not last_data:
            return None
        
        staleness = datetime.now() - last_data
        return staleness.total_seconds() / 60
    
    def get_tracked_contract_ids(self) -> Set[int]:
        """Pure function: Get set of tracked contract IDs"""
        return set(self.tracked_contracts.keys())
    
    def is_contract_tracked(self, contract_id: int) -> bool:
        """Pure function: Check if contract is tracked"""
        return contract_id in self.tracked_contracts
    
    def get_status(self) -> Dict[str, any]:
        """Get health monitor status (pure function)"""
        current_time = datetime.now()
        
        return {
            "tracked_contracts": len(self.tracked_contracts),
            "staleness_threshold_minutes": int(self.staleness_threshold.total_seconds() / 60),
            "contracts_with_data": len(self.last_data_timestamps),
            "last_data_timestamps": {
                contract_id: timestamp.isoformat()
                for contract_id, timestamp in self.last_data_timestamps.items()
            }
        }