"""
Optimized TickMessage data model for v3 storage format.

This module implements the core TickMessage dataclass that reduces storage size
by 50%+ through shortened field names, conditional fields, and flat message structure.
"""

import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_request_id(contract_id: int, tick_type: str, request_time: Optional[int] = None) -> int:
    """
    Generate collision-resistant request ID from request properties.
    
    This creates a deterministic but unique ID that can be used to correlate
    stored data with TWS API logs and prevent conflicts across remote systems.
    
    Args:
        contract_id: IB contract identifier
        tick_type: Tick type (bid_ask, last, all_last, mid_point)
        request_time: Unix timestamp in microseconds (defaults to current time)
        
    Returns:
        32-bit signed integer request ID (safe for IB API)
    """
    if request_time is None:
        request_time = int(time.time() * 1_000_000)
    
    # Create deterministic hash input
    hash_input = f"{contract_id}_{tick_type}_{request_time}".encode('utf-8')
    
    # Generate MD5 hash and take first 4 bytes
    hash_obj = hashlib.md5(hash_input)
    hash_bytes = hash_obj.digest()[:4]
    
    # Convert to signed 32-bit integer (IB API compatible)
    request_id = int.from_bytes(hash_bytes, byteorder='big', signed=True)
    
    # Ensure positive ID for easier debugging
    return abs(request_id)


@dataclass
class TickMessage:
    """
    Optimized tick message format with hash-based request ID tracking.
    
    This format reduces storage size by ~50% compared to v2 protocol through:
    - Shortened field names (ts vs timestamp, cid vs contract_id)
    - Flat message structure (no nested data/metadata objects)
    - Conditional fields (omitted when None/False)
    - Hash-based request IDs instead of complex stream IDs
    """
    
    # Core fields (always present)
    ts: int          # IB timestamp (microseconds since epoch)  
    st: int          # System timestamp (microseconds since epoch)
    cid: int         # Contract ID
    tt: str          # Tick type
    rid: int         # Request ID (hash-generated, collision-resistant)
    
    # Price fields (conditional based on tick type)
    p: Optional[float] = None    # price (last/all_last)
    s: Optional[float] = None    # size (last/all_last) 
    bp: Optional[float] = None   # bid_price
    bs: Optional[float] = None   # bid_size
    ap: Optional[float] = None   # ask_price
    as_: Optional[float] = field(default=None, metadata={'json_key': 'as'})  # ask_size
    mp: Optional[float] = None   # mid_point
    
    # Boolean flags (optional, omitted when false)
    bpl: Optional[bool] = None   # bid_past_low
    aph: Optional[bool] = None   # ask_past_high  
    upt: Optional[bool] = None   # unreported

    def to_json_dict(self) -> Dict[str, Any]:
        """
        Convert to optimized JSON format, omitting None/False values.
        
        This method creates the minimal JSON representation by only including
        fields that have meaningful values, reducing storage size.
        """
        result = {
            'ts': self.ts,
            'st': self.st, 
            'cid': self.cid,
            'tt': self.tt,
            'rid': self.rid
        }
        
        # Add optional fields only if they have meaningful values
        optional_fields = [
            ('p', self.p), ('s', self.s), ('bp', self.bp), ('bs', self.bs),
            ('ap', self.ap), ('as', self.as_), ('mp', self.mp),
            ('bpl', self.bpl), ('aph', self.aph), ('upt', self.upt)
        ]
        
        for field_name, value in optional_fields:
            if value is not None and value is not False:
                result[field_name] = value
                
        return result
        
    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> 'TickMessage':
        """Create TickMessage from optimized JSON format."""
        return cls(
            ts=data['ts'],
            st=data['st'], 
            cid=data['cid'],
            tt=data['tt'],
            rid=data['rid'],
            p=data.get('p'),
            s=data.get('s'),
            bp=data.get('bp'),
            bs=data.get('bs'), 
            ap=data.get('ap'),
            as_=data.get('as'),
            mp=data.get('mp'),
            bpl=data.get('bpl'),
            aph=data.get('aph'),
            upt=data.get('upt')
        )
    
    @classmethod
    def create_from_tick_data(cls, contract_id: int, tick_type: str, 
                             tick_data: Dict[str, Any], request_time: Optional[int] = None) -> 'TickMessage':
        """
        Factory method to create TickMessage from v2 tick data with generated request_id.
        
        This method converts existing v2 formatted tick data into the optimized v3 format,
        mapping the long field names to shortened versions and applying conditional logic.
        """
        if request_time is None:
            request_time = int(time.time() * 1_000_000)
            
        request_id = generate_request_id(contract_id, tick_type, request_time)
        
        # Extract system timestamp (current time in microseconds)
        system_timestamp = int(time.time() * 1_000_000)
        
        # Extract IB timestamp from tick data
        ib_timestamp = tick_data.get('unix_time')
        if ib_timestamp is None:
            # Fallback to system timestamp if IB timestamp not available
            ib_timestamp = system_timestamp
        elif ib_timestamp < 1_000_000_000_000:
            # Convert from seconds to microseconds if needed
            ib_timestamp = int(ib_timestamp * 1_000_000)
        
        # Map tick data fields based on tick type
        mapped_fields = _map_tick_data_fields(tick_data, tick_type)
        
        tick_message = cls(
            ts=ib_timestamp,
            st=system_timestamp,
            cid=contract_id,
            tt=tick_type,
            rid=request_id,
            **mapped_fields
        )
        
        logger.debug(f"Created TickMessage for contract {contract_id}, type {tick_type}, rid {request_id}")
        return tick_message
    
    def to_v2_format(self) -> Dict[str, Any]:
        """
        Convert TickMessage back to v2 protocol format for compatibility.
        
        This is useful for testing and gradual migration where we need to
        serve data in both formats.
        """
        # Create the data section with expanded field names
        data = {
            'contract_id': self.cid,
            'tick_type': self.tt,
            'type': self.tt,
            'unix_time': self.ts,
            'timestamp': datetime.fromtimestamp(self.ts / 1_000_000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        
        # Add tick-type specific fields
        if self.tt in ['bid_ask']:
            if self.bp is not None:
                data['bid_price'] = self.bp
            if self.bs is not None:
                data['bid_size'] = self.bs
            if self.ap is not None:
                data['ask_price'] = self.ap
            if self.as_ is not None:
                data['ask_size'] = self.as_
            if self.bpl is not None:
                data['bid_past_low'] = self.bpl
            if self.aph is not None:
                data['ask_past_high'] = self.aph
                
        elif self.tt in ['last', 'all_last']:
            if self.p is not None:
                data['price'] = self.p
            if self.s is not None:
                data['size'] = self.s
            if self.upt is not None:
                data['unreported'] = self.upt
                
        elif self.tt == 'mid_point':
            if self.mp is not None:
                data['mid_point'] = self.mp
        
        # Create v2 protocol wrapper with metadata
        return {
            'type': 'tick',
            'stream_id': f"{self.cid}_{self.tt}_{self.ts}_{self.rid}",
            'timestamp': datetime.fromtimestamp(self.st / 1_000_000, tz=timezone.utc).isoformat() + 'Z',
            'data': data,
            'metadata': {
                'source': 'v3_storage',
                'request_id': str(self.rid),
                'contract_id': str(self.cid),
                'tick_type': self.tt
            }
        }


def _map_tick_data_fields(tick_data: Dict[str, Any], tick_type: str) -> Dict[str, Any]:
    """
    Map v2 tick data fields to v3 TickMessage fields based on tick type.
    
    This function handles the conditional field mapping logic, ensuring that
    only relevant fields are included for each tick type.
    """
    mapped = {}
    
    if tick_type == 'bid_ask':
        # Bid/Ask specific fields
        if 'bid_price' in tick_data:
            mapped['bp'] = tick_data['bid_price']
        if 'bid_size' in tick_data:
            mapped['bs'] = tick_data['bid_size']
        if 'ask_price' in tick_data:
            mapped['ap'] = tick_data['ask_price']
        if 'ask_size' in tick_data:
            mapped['as_'] = tick_data['ask_size']
        if tick_data.get('bid_past_low'):
            mapped['bpl'] = True
        if tick_data.get('ask_past_high'):
            mapped['aph'] = True
            
    elif tick_type in ['last', 'all_last']:
        # Trade specific fields
        if 'price' in tick_data:
            mapped['p'] = tick_data['price']
        if 'size' in tick_data:
            mapped['s'] = tick_data['size']
        if tick_data.get('unreported'):
            mapped['upt'] = True
            
    elif tick_type == 'mid_point':
        # Mid-point specific fields
        if 'mid_point' in tick_data:
            mapped['mp'] = tick_data['mid_point']
    
    return mapped


def create_tick_message_from_v2(v2_message: Dict[str, Any]) -> Optional[TickMessage]:
    """
    Convert a v2 protocol message to a v3 TickMessage.
    
    This utility function helps with migration by converting existing v2 format
    messages to the optimized v3 format.
    """
    try:
        data = v2_message.get('data', {})
        metadata = v2_message.get('metadata', {})
        
        contract_id = data.get('contract_id')
        tick_type = data.get('tick_type')
        
        if not contract_id or not tick_type:
            logger.warning("Missing contract_id or tick_type in v2 message")
            return None
            
        return TickMessage.create_from_tick_data(
            contract_id=contract_id,
            tick_type=tick_type,
            tick_data=data
        )
        
    except Exception as e:
        logger.error(f"Failed to convert v2 message to TickMessage: {e}")
        return None