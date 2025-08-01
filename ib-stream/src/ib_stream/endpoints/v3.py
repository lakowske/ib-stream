"""
V3 API endpoints for optimized storage format access

This module provides endpoints to access the v3 optimized storage format
with shortened field names and improved storage efficiency.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_v3_endpoints(app, config):
    """Setup v3 API endpoints with dependencies"""
    
    @router.get("/v3/info")
    async def v3_info():
        """Information about the v3 optimized storage format"""
        return {
            "version": "3.0",
            "description": "Optimized storage format with 50%+ size reduction",
            "optimizations": {
                "field_names": "Shortened field names (ts, st, cid, tt, rid)",
                "structure": "Flat structure without nested objects",
                "conditionals": "Optional fields only included when present",
                "storage_reduction": "60-70% size reduction vs v2 format"
            },
            "field_mapping": {
                "ts": "IB timestamp (microseconds since epoch)",
                "st": "System timestamp (microseconds since epoch)", 
                "cid": "Contract ID",
                "tt": "Tick type",
                "rid": "Request ID (hash-generated, collision-resistant)",
                "bp": "Bid price (optional)",
                "bs": "Bid size (optional)", 
                "ap": "Ask price (optional)",
                "as": "Ask size (optional)",
                "p": "Price (optional)",
                "s": "Size (optional)",
                "mp": "Mid point (optional)"
            },
            "formats": ["json", "protobuf"],
            "endpoints": {
                "/v3/buffer/{contract_id}/query": "Query v3 buffer data with time range",
                "/v3/buffer/{contract_id}/info": "V3 buffer information and statistics",
                "/v3/storage/stats": "V3 storage statistics and comparison with v2",
                "/v3/storage/files": "List v3 storage files for a contract"
            }
        }
    
    @router.get("/v3/buffer/{contract_id}/info")
    async def v3_buffer_info(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types")
    ):
        """Get v3 buffer information for a contract"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        try:
            # Check v3 storage paths
            v3_storage_path = config.storage.storage_base_path / "v3"
            
            info = {
                "contract_id": contract_id,
                "tick_types": tick_type_list,
                "v3_storage": {
                    "json_path": str(v3_storage_path / "json"),
                    "protobuf_path": str(v3_storage_path / "protobuf"),
                    "available_formats": []
                },
                "files": {},
                "statistics": {}
            }
            
            # Check available formats and files
            for format_name in ["json", "protobuf"]:
                format_path = v3_storage_path / format_name
                if format_path.exists():
                    info["v3_storage"]["available_formats"].append(format_name)
                    
                    # Find files for this contract
                    contract_files = []
                    for tick_type in tick_type_list:
                        # Search for files matching contract_id and tick_type pattern
                        pattern = f"{contract_id}_{tick_type}_*"
                        ext = ".jsonl" if format_name == "json" else ".pb"
                        
                        for file_path in format_path.rglob(f"*{pattern}{ext}"):
                            file_info = {
                                "path": str(file_path.relative_to(format_path)),
                                "size_bytes": file_path.stat().st_size,
                                "modified": datetime.fromtimestamp(
                                    file_path.stat().st_mtime, tz=timezone.utc
                                ).isoformat()
                            }
                            contract_files.append(file_info)
                    
                    info["files"][format_name] = contract_files
                    
                    # Calculate statistics
                    total_size = sum(f["size_bytes"] for f in contract_files)
                    info["statistics"][format_name] = {
                        "total_files": len(contract_files),
                        "total_size_bytes": total_size,
                        "total_size_mb": round(total_size / (1024 * 1024), 2)
                    }
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting v3 buffer info for contract {contract_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get v3 buffer information: {str(e)}"
            )
    
    @router.get("/v3/buffer/{contract_id}/query")
    async def v3_buffer_query(
        contract_id: int,
        tick_types: str = Query(default="bid_ask", description="Comma-separated tick types"),
        format: str = Query(default="json", description="Storage format: json or protobuf"),
        start_time: Optional[str] = Query(default=None, description="Start time (ISO format)"),
        end_time: Optional[str] = Query(default=None, description="End time (ISO format)"),
        buffer_duration: str = Query(default="1h", description="Buffer duration (e.g., 1h, 30m, 2h)"),
        limit: Optional[int] = Query(default=None, description="Maximum number of records"),
        raw: bool = Query(default=False, description="Return raw v3 format (true) or expanded format (false)")
    ):
        """Query v3 buffer data with time range and format options"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        # Validate format
        if format not in ["json", "protobuf"]:
            raise HTTPException(
                status_code=400,
                detail="Format must be 'json' or 'protobuf'"
            )
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        try:
            # Calculate time range
            if start_time and end_time:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            else:
                end_dt = datetime.now(timezone.utc)
                start_dt = end_dt - _parse_duration(buffer_duration)
            
            # Query v3 storage directly
            v3_storage_path = config.storage.storage_base_path / "v3" / format
            
            if not v3_storage_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"V3 {format} storage not found"
                )
            
            # Collect matching files and read data
            all_messages = []
            
            for tick_type in tick_type_list:
                file_pattern = f"{contract_id}_{tick_type}_*"
                ext = ".jsonl" if format == "json" else ".pb"
                
                for file_path in v3_storage_path.rglob(f"*{file_pattern}{ext}"):
                    try:
                        if format == "json":
                            messages = await _read_v3_json_file(file_path, start_dt, end_dt, raw)
                        else:
                            messages = await _read_v3_protobuf_file(file_path, start_dt, end_dt, raw)
                        
                        all_messages.extend(messages)
                        
                    except Exception as e:
                        logger.warning(f"Error reading v3 file {file_path}: {e}")
                        continue
            
            # Sort by timestamp and apply limit
            all_messages.sort(key=lambda x: x.get('ts' if raw else 'timestamp', 0))
            
            if limit:
                all_messages = all_messages[:limit]
            
            return {
                "contract_id": contract_id,
                "tick_types": tick_type_list,
                "format": format,
                "time_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat()
                },
                "total_messages": len(all_messages),
                "raw_format": raw,
                "messages": all_messages
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error querying v3 buffer for contract {contract_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query v3 buffer: {str(e)}"
            )
    
    @router.get("/v3/storage/stats") 
    async def v3_storage_stats():
        """Get v3 storage statistics and comparison with v2"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            # Get storage information from MultiStorageV3
            storage_info = await storage.get_storage_info()
            
            return {
                "v3_storage_stats": storage_info,
                "optimization_summary": {
                    "target_reduction": "50%+",
                    "achieved_reduction": f"{storage_info.get('storage_comparison', {}).get('savings_percent', 0):.1f}%",
                    "formats_supported": ["json", "protobuf"],
                    "parallel_storage": "v2 + v3 simultaneously"
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting v3 storage stats: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get v3 storage statistics: {str(e)}"
            )
    
    @router.get("/v3/storage/files/{contract_id}")
    async def v3_storage_files(
        contract_id: int,
        format: str = Query(default="json", description="Storage format: json or protobuf"),
        tick_type: Optional[str] = Query(default=None, description="Specific tick type filter")
    ):
        """List v3 storage files for a contract"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        
        if format not in ["json", "protobuf"]:
            raise HTTPException(
                status_code=400,
                detail="Format must be 'json' or 'protobuf'"
            )
        
        try:
            v3_storage_path = config.storage.storage_base_path / "v3" / format
            
            if not v3_storage_path.exists():
                return {
                    "contract_id": contract_id,
                    "format": format,
                    "files": [],
                    "message": f"V3 {format} storage directory not found"
                }
            
            # Build file pattern
            if tick_type:
                pattern = f"{contract_id}_{tick_type}_*"
            else:
                pattern = f"{contract_id}_*"
            
            ext = ".jsonl" if format == "json" else ".pb"
            
            files = []
            for file_path in v3_storage_path.rglob(f"*{pattern}{ext}"):
                file_info = {
                    "filename": file_path.name,
                    "relative_path": str(file_path.relative_to(v3_storage_path)),
                    "size_bytes": file_path.stat().st_size,
                    "size_mb": round(file_path.stat().st_size / (1024 * 1024), 4),
                    "modified": datetime.fromtimestamp(
                        file_path.stat().st_mtime, tz=timezone.utc
                    ).isoformat()
                }
                files.append(file_info)
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: x["modified"], reverse=True)
            
            return {
                "contract_id": contract_id,
                "format": format,
                "tick_type_filter": tick_type,
                "total_files": len(files),
                "total_size_mb": round(sum(f["size_bytes"] for f in files) / (1024 * 1024), 2),
                "files": files
            }
            
        except Exception as e:
            logger.error(f"Error listing v3 storage files for contract {contract_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list v3 storage files: {str(e)}"
            )
    
    # Add router to app
    app.include_router(router, prefix="", tags=["v3"])


async def _read_v3_json_file(file_path: Path, start_dt: datetime, end_dt: datetime, raw: bool) -> List[Dict[str, Any]]:
    """Read and filter v3 JSON file"""
    import json
    
    messages = []
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            try:
                message = json.loads(line)
                
                # Filter by timestamp (ts is in microseconds)
                ts_us = message.get('ts', 0)
                ts_dt = datetime.fromtimestamp(ts_us / 1_000_000, tz=timezone.utc)
                
                if start_dt <= ts_dt <= end_dt:
                    if raw:
                        messages.append(message)
                    else:
                        # Expand to readable format
                        expanded = _expand_v3_message(message)
                        messages.append(expanded)
                        
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error in {file_path}: {e}")
                continue
    
    return messages


async def _read_v3_protobuf_file(file_path: Path, start_dt: datetime, end_dt: datetime, raw: bool) -> List[Dict[str, Any]]:
    """Read and filter v3 Protobuf file"""
    from ..storage.proto.tick_message_v3_pb2 import TickMessage
    import struct
    
    messages = []
    
    with open(file_path, 'rb') as f:
        while True:
            # Read length prefix
            length_data = f.read(4)
            if len(length_data) < 4:
                break
                
            length = struct.unpack('<I', length_data)[0]
            
            # Read message
            message_data = f.read(length)
            if len(message_data) < length:
                break
            
            try:
                proto_message = TickMessage()
                proto_message.ParseFromString(message_data)
                
                # Filter by timestamp
                ts_dt = datetime.fromtimestamp(proto_message.ts / 1_000_000, tz=timezone.utc)
                
                if start_dt <= ts_dt <= end_dt:
                    if raw:
                        # Convert protobuf to dict in v3 format
                        message = _proto_to_v3_dict(proto_message)
                        messages.append(message)
                    else:
                        # Expand to readable format
                        message = _proto_to_v3_dict(proto_message)
                        expanded = _expand_v3_message(message)
                        messages.append(expanded)
                        
            except Exception as e:
                logger.warning(f"Protobuf decode error in {file_path}: {e}")
                continue
    
    return messages


def _proto_to_v3_dict(proto_message) -> Dict[str, Any]:
    """Convert protobuf message to v3 dict format"""
    message = {
        "ts": proto_message.ts,
        "st": proto_message.st,
        "cid": proto_message.cid,
        "tt": proto_message.tt,
        "rid": proto_message.rid
    }
    
    # Add optional fields only if present
    if proto_message.HasField("bp"):
        message["bp"] = proto_message.bp
    if proto_message.HasField("bs"):
        message["bs"] = proto_message.bs
    if proto_message.HasField("ap"):
        message["ap"] = proto_message.ap
    if proto_message.HasField("as"):
        message["as"] = getattr(proto_message, "as")  # 'as' is reserved keyword
    if proto_message.HasField("p"):
        message["p"] = proto_message.p
    if proto_message.HasField("s"):
        message["s"] = proto_message.s
    if proto_message.HasField("mp"):
        message["mp"] = proto_message.mp
    
    return message


def _expand_v3_message(v3_message: Dict[str, Any]) -> Dict[str, Any]:
    """Expand v3 message to readable format with full field names"""
    expanded = {
        "ib_timestamp": v3_message.get("ts"),
        "ib_timestamp_iso": datetime.fromtimestamp(
            v3_message.get("ts", 0) / 1_000_000, tz=timezone.utc
        ).isoformat() if v3_message.get("ts") else None,
        "system_timestamp": v3_message.get("st"),
        "system_timestamp_iso": datetime.fromtimestamp(
            v3_message.get("st", 0) / 1_000_000, tz=timezone.utc
        ).isoformat() if v3_message.get("st") else None,
        "contract_id": v3_message.get("cid"),
        "tick_type": v3_message.get("tt"),
        "request_id": v3_message.get("rid")
    }
    
    # Add optional fields with full names
    if "bp" in v3_message:
        expanded["bid_price"] = v3_message["bp"]
    if "bs" in v3_message:
        expanded["bid_size"] = v3_message["bs"]
    if "ap" in v3_message:
        expanded["ask_price"] = v3_message["ap"]
    if "as" in v3_message:
        expanded["ask_size"] = v3_message["as"]
    if "p" in v3_message:
        expanded["price"] = v3_message["p"]
    if "s" in v3_message:
        expanded["size"] = v3_message["s"]
    if "mp" in v3_message:
        expanded["mid_point"] = v3_message["mp"]
    
    return expanded


def _parse_duration(duration_str: str) -> timedelta:
    """Parse duration string (e.g., '1h', '30m', '2h') to timedelta"""
    duration_str = duration_str.lower().strip()
    
    if duration_str.endswith('h'):
        hours = int(duration_str[:-1])
        return timedelta(hours=hours)
    elif duration_str.endswith('m'):
        minutes = int(duration_str[:-1])
        return timedelta(minutes=minutes)
    elif duration_str.endswith('d'):
        days = int(duration_str[:-1])
        return timedelta(days=days)
    else:
        # Default to hours if no unit specified
        hours = int(duration_str)
        return timedelta(hours=hours)