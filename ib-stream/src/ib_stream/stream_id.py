"""
Stream ID generation for IB-Stream v2 protocol.
Follows the pattern: {contract_id}_{tick_type}_{timestamp}_{random}
"""

import random
import time
from typing import List, Optional


def normalize_tick_type(tick_type: str) -> str:
    """Normalize tick type to snake_case format."""
    # Convert common IB API tick types to v2 format
    tick_type_map = {
        'BidAsk': 'bid_ask',
        'Last': 'last', 
        'AllLast': 'all_last',
        'MidPoint': 'mid_point'
    }
    
    return tick_type_map.get(tick_type, tick_type.lower())


def generate_stream_id(contract_id: int, tick_type: str) -> str:
    """
    Generate unique stream identifier following v2 protocol.
    
    Args:
        contract_id: IB contract identifier
        tick_type: Type of tick data (bid_ask, last, all_last, mid_point)
        
    Returns:
        Stream ID in format: {contract_id}_{tick_type}_{timestamp}_{random}
    """
    normalized_tick_type = normalize_tick_type(tick_type)
    timestamp = int(time.time() * 1000)
    random_suffix = random.randint(1000, 9999)
    
    return f"{contract_id}_{normalized_tick_type}_{timestamp}_{random_suffix}"


def generate_multi_stream_id(contract_id: int, tick_types: List[str]) -> str:
    """
    Generate stream ID for multi-tick-type streams.
    
    Args:
        contract_id: IB contract identifier
        tick_types: List of tick types
        
    Returns:
        Stream ID with multi indicator
    """
    # Sort tick types for consistency
    sorted_types = sorted(normalize_tick_type(t) for t in tick_types)
    multi_type = "multi_" + "_".join(sorted_types)
    
    timestamp = int(time.time() * 1000)
    random_suffix = random.randint(1000, 9999)
    
    return f"{contract_id}_{multi_type}_{timestamp}_{random_suffix}"


def parse_stream_id(stream_id: str) -> Optional[dict]:
    """
    Parse stream ID to extract components.
    
    Args:
        stream_id: Stream ID to parse
        
    Returns:
        Dictionary with parsed components or None if invalid
    """
    try:
        parts = stream_id.split('_')
        if len(parts) < 4:
            return None
            
        contract_id = int(parts[0])
        
        # Find timestamp (second to last part)
        timestamp = int(parts[-2])
        random_suffix = int(parts[-1])
        
        # Everything between contract_id and timestamp is tick_type
        tick_type = '_'.join(parts[1:-2])
        
        return {
            'contract_id': contract_id,
            'tick_type': tick_type,
            'timestamp': timestamp,
            'random': random_suffix
        }
    except (ValueError, IndexError):
        return None


def extract_contract_id(stream_id: str) -> Optional[int]:
    """Extract contract ID from stream ID."""
    parsed = parse_stream_id(stream_id)
    return parsed['contract_id'] if parsed else None


def extract_tick_type(stream_id: str) -> Optional[str]:
    """Extract tick type from stream ID."""
    parsed = parse_stream_id(stream_id)
    return parsed['tick_type'] if parsed else None