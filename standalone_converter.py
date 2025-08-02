#!/usr/bin/env python3
"""
Standalone V2 to V3 Storage Converter

This is a self-contained converter that doesn't require external dependencies.
It implements the core conversion logic to demonstrate the v2 to v3 migration.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


# Note: We preserve the original IB API request_id from v2 metadata
# No hash generation needed - direct preservation maintains TWS correlation


@dataclass
class TickMessage:
    """Optimized tick message format for v3 storage."""
    
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
    as_: Optional[float] = None  # ask_size (as_ because 'as' is reserved)
    mp: Optional[float] = None   # mid_point
    
    # Boolean flags (optional, omitted when false)
    bpl: Optional[bool] = None   # bid_past_low
    aph: Optional[bool] = None   # ask_past_high  
    upt: Optional[bool] = None   # unreported

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to optimized JSON format, omitting None/False values."""
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


def convert_v2_message_to_v3(v2_message: Dict[str, Any]) -> Optional[TickMessage]:
    """Convert a v2 protocol message to a v3 TickMessage."""
    try:
        data = v2_message.get('data', {})
        metadata = v2_message.get('metadata', {})
        
        # Get contract_id and tick_type from metadata
        contract_id = metadata.get('contract_id')
        tick_type = metadata.get('tick_type')
        
        # Convert string IDs to integers
        if isinstance(contract_id, str):
            contract_id = int(contract_id)
        
        if not contract_id or not tick_type:
            print(f"WARNING: Missing contract_id or tick_type in message")
            return None
        
        # Use original IB API request_id from v2 metadata
        original_request_id = metadata.get('request_id')
        if not original_request_id:
            print(f"WARNING: No request_id found in metadata")
            return None
        
        # Convert to integer if it's a string
        try:
            request_id = int(original_request_id)
        except (ValueError, TypeError):
            print(f"WARNING: Invalid request_id format: {original_request_id}")
            return None
        
        # Extract IB timestamp from data  
        system_timestamp = int(time.time() * 1_000_000)
        ib_timestamp = data.get('unix_time', system_timestamp)
        if ib_timestamp < 1_000_000_000_000:
            # Convert from seconds to microseconds if needed
            ib_timestamp = int(ib_timestamp * 1_000_000)
        
        # Map tick data fields based on tick type
        mapped_fields = {}
        
        if tick_type == 'bid_ask':
            # Bid/Ask specific fields
            if 'bid_price' in data:
                mapped_fields['bp'] = data['bid_price']
            if 'bid_size' in data:
                mapped_fields['bs'] = data['bid_size']
            if 'ask_price' in data:
                mapped_fields['ap'] = data['ask_price']
            if 'ask_size' in data:
                mapped_fields['as_'] = data['ask_size']
            if data.get('bid_past_low'):
                mapped_fields['bpl'] = True
            if data.get('ask_past_high'):
                mapped_fields['aph'] = True
                
        elif tick_type in ['last', 'all_last']:
            # Trade specific fields
            if 'price' in data:
                mapped_fields['p'] = data['price']
            if 'size' in data:
                mapped_fields['s'] = data['size']
            if data.get('unreported'):
                mapped_fields['upt'] = True
                
        elif tick_type == 'mid_point':
            # Mid-point specific fields
            if 'mid_point' in data:
                mapped_fields['mp'] = data['mid_point']
        
        return TickMessage(
            ts=ib_timestamp,
            st=system_timestamp,
            cid=contract_id,
            tt=tick_type,
            rid=request_id,
            **mapped_fields
        )
        
    except Exception as e:
        print(f"ERROR: Failed to convert v2 message: {e}")
        return None


def convert_file(v2_file_path: Path, v3_output_path: Path) -> Dict[str, Any]:
    """Convert a single v2 file to v3 format."""
    stats = {
        'source_file': str(v2_file_path),
        'target_file': str(v3_output_path),
        'messages_processed': 0,
        'messages_converted': 0,
        'messages_failed': 0,
        'source_size_bytes': v2_file_path.stat().st_size,
        'target_size_bytes': 0,
        'errors': []
    }
    
    print(f"Converting {v2_file_path} -> {v3_output_path}")
    
    try:
        # Ensure output directory exists
        v3_output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(v2_file_path, 'r', encoding='utf-8') as infile, \
             open(v3_output_path, 'w', encoding='utf-8') as outfile:
            
            for line_num, line in enumerate(infile, 1):
                line = line.strip()
                if not line:
                    continue
                
                stats['messages_processed'] += 1
                
                try:
                    v2_message = json.loads(line)
                    tick_message = convert_v2_message_to_v3(v2_message)
                    
                    if tick_message:
                        v3_json = tick_message.to_json_dict()
                        json_line = json.dumps(v3_json, separators=(',', ':'))
                        outfile.write(json_line + '\n')
                        stats['messages_converted'] += 1
                    else:
                        stats['messages_failed'] += 1
                        
                except json.JSONDecodeError as e:
                    stats['messages_failed'] += 1
                    error_msg = f"JSON decode error at line {line_num}: {e}"
                    stats['errors'].append(error_msg)
                except Exception as e:
                    stats['messages_failed'] += 1
                    error_msg = f"Conversion error at line {line_num}: {e}"
                    stats['errors'].append(error_msg)
        
        # Get target file size
        if v3_output_path.exists():
            stats['target_size_bytes'] = v3_output_path.stat().st_size
        
        print(f"  Processed: {stats['messages_processed']}")
        print(f"  Converted: {stats['messages_converted']}")
        print(f"  Failed: {stats['messages_failed']}")
        print(f"  Size reduction: {stats['source_size_bytes']} -> {stats['target_size_bytes']} bytes")
        
        return stats
        
    except Exception as e:
        error_msg = f"File conversion error: {e}"
        stats['errors'].append(error_msg)
        print(f"ERROR: {error_msg}")
        return stats


def main():
    """Test the standalone converter with sample data."""
    print("Standalone V2 to V3 Converter Test")
    print("=" * 50)
    
    # Use existing v2 data
    v2_storage_path = Path('/workspace/storage/v2')
    v3_storage_path = Path('/workspace/storage/v3')
    
    if not v2_storage_path.exists():
        print("ERROR: V2 storage path not found")
        return 1
    
    # Find v2 files
    json_files = list(v2_storage_path.rglob('*.jsonl'))
    print(f"Found {len(json_files)} v2 JSON files")
    
    if not json_files:
        print("ERROR: No JSON files found")
        return 1
    
    # Convert a few sample files
    sample_files = json_files[:5]  # Convert first 5 files as test
    
    total_stats = {
        'files_processed': 0,
        'messages_converted': 0,
        'messages_failed': 0,
        'source_size_bytes': 0,
        'target_size_bytes': 0
    }
    
    for v2_file in sample_files:
        # Create corresponding v3 file path
        relative_path = v2_file.relative_to(v2_storage_path)
        v3_file = v3_storage_path / 'json' / relative_path
        
        # Convert file
        file_stats = convert_file(v2_file, v3_file)
        
        # Update totals
        total_stats['files_processed'] += 1
        total_stats['messages_converted'] += file_stats['messages_converted']
        total_stats['messages_failed'] += file_stats['messages_failed']
        total_stats['source_size_bytes'] += file_stats['source_size_bytes']
        total_stats['target_size_bytes'] += file_stats['target_size_bytes']
    
    # Print summary
    print("\n" + "=" * 50)
    print("Conversion Summary:")
    print(f"Files processed: {total_stats['files_processed']}")
    print(f"Messages converted: {total_stats['messages_converted']:,}")
    print(f"Messages failed: {total_stats['messages_failed']:,}")
    
    if total_stats['source_size_bytes'] > 0:
        source_mb = total_stats['source_size_bytes'] / (1024 * 1024)
        target_mb = total_stats['target_size_bytes'] / (1024 * 1024)
        compression_ratio = total_stats['target_size_bytes'] / total_stats['source_size_bytes']
        space_saved_percent = (1 - compression_ratio) * 100
        
        print(f"Source size: {source_mb:.2f} MB")
        print(f"Target size: {target_mb:.2f} MB")
        print(f"Space saved: {space_saved_percent:.1f}%")
    
    print(f"\nConverted files saved to: {v3_storage_path}")
    
    return 0


if __name__ == '__main__':
    exit(main())