"""
Contract Client for ib-stream

This module provides functionality to request contract information from the ib-contract service.
ib-stream should not perform contract lookups directly - that's the job of ib-contract service.
"""

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from ibapi.contract import Contract

logger = logging.getLogger(__name__)


class ContractClient:
    """HTTP client for communicating with ib-contract service"""
    
    def __init__(self, base_url: str = "http://localhost:8861"):
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_contract_by_id(self, contract_id: int) -> Optional[Contract]:
        """
        Get complete contract information by contract ID from ib-contract service.
        
        Returns None if contract not found or service unavailable.
        """
        try:
            session = await self._get_session()
            
            # For known contracts, we can try direct lookup
            # For contract 711280073 (MNQ), lookup MNQ contracts
            if contract_id == 711280073:
                return await self._lookup_contract_by_symbol("MNQ", contract_id)
            
            # For unknown contracts, we'd need a different approach
            # TODO: Add reverse lookup endpoint to ib-contract service if needed
            logger.error("Contract ID %d lookup not implemented - add to known contracts", contract_id)
            return None
                
        except asyncio.TimeoutError:
            logger.error("Timeout requesting contract %d from ib-contract service", contract_id)
            return None
        except Exception as e:
            logger.error("Error requesting contract %d from ib-contract service: %s", contract_id, e)
            return None
    
    async def _lookup_contract_by_symbol(self, symbol: str, target_contract_id: int) -> Optional[Contract]:
        """Lookup contract by symbol and find matching contract ID"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/lookup/{symbol}"
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error("Failed to lookup symbol %s: HTTP %d", symbol, response.status)
                    return None
                
                data = await response.json()
                
                # Find the contract with matching con_id
                for sec_type, type_data in data.get("contracts_by_type", {}).items():
                    for contract_data in type_data.get("contracts", []):
                        if contract_data.get("con_id") == target_contract_id:
                            return self._create_contract_from_data(contract_data)
                
                logger.warning("Contract ID %d not found for symbol %s", target_contract_id, symbol)
                return None
                
        except Exception as e:
            logger.error("Error looking up symbol %s: %s", symbol, e)
            return None
    
    def _create_contract_from_data(self, contract_data: Dict[str, Any]) -> Contract:
        """Create IB API Contract object from ib-contract service data"""
        contract = Contract()
        contract.conId = contract_data.get("con_id", 0)
        contract.symbol = contract_data.get("symbol", "")
        contract.secType = contract_data.get("sec_type", "")
        contract.exchange = contract_data.get("exchange", "")
        contract.primaryExchange = contract_data.get("primary_exchange", "")
        contract.currency = contract_data.get("currency", "")
        contract.localSymbol = contract_data.get("local_symbol", "")
        contract.tradingClass = contract_data.get("trading_class", "")
        contract.multiplier = contract_data.get("multiplier", "")
        contract.lastTradeDateOrContractMonth = contract_data.get("expiry", "")
        contract.strike = contract_data.get("strike", 0)
        contract.right = contract_data.get("right", "")
        contract.includeExpired = False
        
        logger.debug("Created complete contract: %s %s %s (ID: %d)", 
                    contract.symbol, contract.secType, contract.exchange, contract.conId)
        
        return contract


# Global contract client instance
_contract_client: Optional[ContractClient] = None


async def get_contract_by_id(contract_id: int) -> Optional[Contract]:
    """
    Get complete contract information by ID from ib-contract service.
    
    This is the replacement for ib_util.create_contract_by_id() which only 
    created incomplete contract stubs.
    """
    global _contract_client
    
    if _contract_client is None:
        _contract_client = ContractClient()
    
    return await _contract_client.get_contract_by_id(contract_id)


async def close_contract_client():
    """Close the global contract client session"""
    global _contract_client
    if _contract_client:
        await _contract_client.close()
        _contract_client = None