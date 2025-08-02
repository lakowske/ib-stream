#!/usr/bin/env python3
"""
Data Integrity Validation for V2 to V3 Conversion

This script validates that the converted v3 data maintains the same information
as the original v2 data with no data loss.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


def compare_message_data(v2_message: Dict[str, Any], v3_message: Dict[str, Any]) -> List[str]:
    """
    Compare v2 and v3 messages to ensure data integrity.
    
    Returns:
        List of error messages if data doesn't match, empty list if valid
    """
    errors = []
    
    try:
        # Extract v2 data
        v2_data = v2_message.get('data', {})
        v2_metadata = v2_message.get('metadata', {})
        
        # Check core fields
        v2_contract_id = int(v2_metadata.get('contract_id', 0))
        v2_tick_type = v2_metadata.get('tick_type', '')
        v2_timestamp = v2_data.get('unix_time', 0)
        
        if v2_timestamp < 1_000_000_000_000:
            v2_timestamp *= 1_000_000  # Convert to microseconds
        
        if v3_message.get('cid') != v2_contract_id:
            errors.append(f"Contract ID mismatch: v2={v2_contract_id}, v3={v3_message.get('cid')}")
        
        if v3_message.get('tt') != v2_tick_type:
            errors.append(f"Tick type mismatch: v2={v2_tick_type}, v3={v3_message.get('tt')}")
        
        if v3_message.get('ts') != v2_timestamp:
            errors.append(f"Timestamp mismatch: v2={v2_timestamp}, v3={v3_message.get('ts')}")
        
        # Check tick-type specific fields
        if v2_tick_type == 'bid_ask':
            # Check bid/ask fields
            if 'bid_price' in v2_data and v3_message.get('bp') != v2_data['bid_price']:
                errors.append(f"Bid price mismatch: v2={v2_data['bid_price']}, v3={v3_message.get('bp')}")
            
            if 'ask_price' in v2_data and v3_message.get('ap') != v2_data['ask_price']:
                errors.append(f"Ask price mismatch: v2={v2_data['ask_price']}, v3={v3_message.get('ap')}")
            
            if 'bid_size' in v2_data and v3_message.get('bs') != v2_data['bid_size']:
                errors.append(f"Bid size mismatch: v2={v2_data['bid_size']}, v3={v3_message.get('bs')}")
            
            if 'ask_size' in v2_data and v3_message.get('as') != v2_data['ask_size']:
                errors.append(f"Ask size mismatch: v2={v2_data['ask_size']}, v3={v3_message.get('as')}")
            
            # Check boolean flags
            if v2_data.get('bid_past_low', False):
                if not v3_message.get('bpl'):
                    errors.append("Bid past low flag lost in conversion")
            elif v3_message.get('bpl'):
                errors.append("Bid past low flag incorrectly set in v3")
            
            if v2_data.get('ask_past_high', False):
                if not v3_message.get('aph'):
                    errors.append("Ask past high flag lost in conversion")
            elif v3_message.get('aph'):
                errors.append("Ask past high flag incorrectly set in v3")
        
        elif v2_tick_type in ['last', 'all_last']:
            # Check trade fields
            if 'price' in v2_data and v3_message.get('p') != v2_data['price']:
                errors.append(f"Price mismatch: v2={v2_data['price']}, v3={v3_message.get('p')}")
            
            if 'size' in v2_data and v3_message.get('s') != v2_data['size']:
                errors.append(f"Size mismatch: v2={v2_data['size']}, v3={v3_message.get('s')}")
            
            # Check unreported flag
            if v2_data.get('unreported', False):
                if not v3_message.get('upt'):
                    errors.append("Unreported flag lost in conversion")
            elif v3_message.get('upt'):
                errors.append("Unreported flag incorrectly set in v3")
        
    except Exception as e:
        errors.append(f"Comparison error: {e}")
    
    return errors


def validate_conversion_integrity(v2_file: Path, v3_file: Path) -> Dict[str, Any]:
    """
    Validate that v3 file contains exactly the same data as v2 file.
    
    Returns:
        Dictionary with validation results
    """
    results = {
        'v2_file': str(v2_file),
        'v3_file': str(v3_file),
        'v2_messages': 0,
        'v3_messages': 0,
        'matches': 0,
        'errors': [],
        'valid': True
    }
    
    try:
        # Read both files
        v2_messages = []
        v3_messages = []
        
        with open(v2_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    v2_messages.append(json.loads(line))
        
        with open(v3_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    v3_messages.append(json.loads(line))
        
        results['v2_messages'] = len(v2_messages)
        results['v3_messages'] = len(v3_messages)
        
        # Check message count
        if len(v2_messages) != len(v3_messages):
            error_msg = f"Message count mismatch: v2={len(v2_messages)}, v3={len(v3_messages)}"
            results['errors'].append(error_msg)
            results['valid'] = False
            return results
        
        # Compare each message pair
        for i, (v2_msg, v3_msg) in enumerate(zip(v2_messages, v3_messages)):
            comparison_errors = compare_message_data(v2_msg, v3_msg)
            
            if comparison_errors:
                results['errors'].extend([f"Message {i+1}: {err}" for err in comparison_errors])
                results['valid'] = False
            else:
                results['matches'] += 1
        
        print(f"Validated {results['v2_messages']} messages: {results['matches']} matches, {len(results['errors'])} errors")
        
    except Exception as e:
        results['errors'].append(f"Validation error: {e}")
        results['valid'] = False
    
    return results


def main():
    """Run integrity validation on converted files."""
    print("V2 to V3 Conversion Integrity Validation")
    print("=" * 50)
    
    v2_base = Path('/workspace/storage/v2/json')
    v3_base = Path('/workspace/storage/v3/json/json')  # Note: extra 'json' from our test
    
    if not v2_base.exists():
        print("ERROR: V2 storage not found")
        return 1
    
    if not v3_base.exists():
        print("ERROR: V3 storage not found")
        return 1
    
    # Find corresponding file pairs
    v2_files = list(v2_base.rglob('*.jsonl'))
    print(f"Found {len(v2_files)} v2 files")
    
    validated_files = 0
    total_errors = 0
    
    for v2_file in v2_files:
        # Find corresponding v3 file
        relative_path = v2_file.relative_to(v2_base)
        v3_file = v3_base / relative_path
        
        if v3_file.exists():
            print(f"\nValidating: {relative_path}")
            validation_results = validate_conversion_integrity(v2_file, v3_file)
            
            validated_files += 1
            total_errors += len(validation_results['errors'])
            
            if not validation_results['valid']:
                print(f"  VALIDATION FAILED:")
                for error in validation_results['errors'][:5]:  # Show first 5 errors
                    print(f"    {error}")
                if len(validation_results['errors']) > 5:
                    print(f"    ... and {len(validation_results['errors']) - 5} more errors")
            else:
                print(f"  ✓ VALID: {validation_results['matches']} messages verified")
        else:
            print(f"WARNING: No corresponding v3 file for {relative_path}")
    
    print("\n" + "=" * 50)
    print("Validation Summary:")
    print(f"Files validated: {validated_files}")
    print(f"Total errors: {total_errors}")
    
    if total_errors == 0:
        print("✓ All validations passed - data integrity confirmed!")
        return 0
    else:
        print("✗ Validation failures detected - data integrity issues found!")
        return 1


if __name__ == '__main__':
    exit(main())