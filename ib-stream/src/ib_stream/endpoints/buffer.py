"""
Buffer and storage query endpoints for the IB Stream API
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from ..storage import create_buffer_query

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_buffer_endpoints(app, config):
    """Setup buffer and storage query endpoints with dependencies"""
    
    @router.get("/v2/buffer/{contract_id}/info")
    async def buffer_info(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types")
    ):
        """Get buffer information for a contract with stored data"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        background_manager = app_state['background_manager']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            # Get buffer information
            available_duration = buffer_query.get_available_buffer_duration(contract_id, tick_type_list)
            latest_tick_time = buffer_query.get_latest_tick_time(contract_id, tick_type_list)
            buffer_stats_1h = await buffer_query.get_buffer_stats(contract_id, tick_type_list, "1h")
            
            # Get configured buffer hours from background manager (if available)
            configured_buffer_hours = None
            if background_manager and background_manager.is_contract_tracked(contract_id):
                configured_buffer_hours = background_manager.get_contract_buffer_hours(contract_id)
            
            return {
                "contract_id": contract_id,
                "tick_types": tick_type_list,
                "tracked": True,
                "available_duration": str(available_duration) if available_duration else None,
                "configured_buffer_hours": configured_buffer_hours,
                "latest_tick_time": latest_tick_time.isoformat() if latest_tick_time else None,
                "buffer_stats_1h": buffer_stats_1h,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Buffer info error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )

    @router.get("/v2/buffer/{contract_id}/stats")
    async def buffer_stats(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
        duration: str = Query(default="1h", description="Duration to analyze"),
        storage_type: str = Query(default="json", description="Storage type: json, protobuf, or both")
    ):
        """Get detailed buffer statistics for a contract with stored data"""
        from ..app_lifecycle import get_app_state
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            stats = await buffer_query.get_buffer_stats(contract_id, tick_type_list, duration, storage_type)
            
            return {
                "contract_id": contract_id,
                "statistics": stats,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Buffer stats error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/v2/buffer/{contract_id}/range")
    async def buffer_range_query(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
        start_time: str = Query(..., description="Start time in ISO format (e.g., 2025-07-25T12:00:00Z) or with timezone (e.g., 2025-07-25T12:00:00-05:00)"),
        end_time: str = Query(None, description="End time in ISO format (optional if duration provided)"),
        duration: str = Query(None, description="Duration from start_time (e.g., '1m', '5m', '1h')"),
        storage_type: str = Query(default="json", description="Storage type: json, protobuf, or both"),
        tz: str = Query(default=None, description="Timezone for interpreting start_time/end_time if no timezone specified (e.g., 'America/New_York', 'UTC')"),
        limit: Optional[int] = Query(default=None, description="Maximum number of messages to return")
    ):
        """Get buffer data for a specific time range"""
        from ..app_lifecycle import get_app_state
        from datetime import datetime, timezone, timedelta
        import re
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            # Fallback for Python < 3.9
            from backports.zoneinfo import ZoneInfo
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            # Parse start_time with timezone support
            def parse_datetime_with_tz(dt_str: str, default_tz_name: str = None) -> datetime:
                """Parse datetime string with optional timezone support"""
                try:
                    if dt_str.endswith('Z'):
                        # UTC timezone
                        return datetime.fromisoformat(dt_str[:-1]).replace(tzinfo=timezone.utc)
                    elif '+' in dt_str[-6:] or dt_str[-6:-3] == '-':
                        # Has timezone offset (e.g., +05:00 or -04:00)
                        return datetime.fromisoformat(dt_str)
                    else:
                        # No timezone specified - use provided timezone or UTC
                        dt = datetime.fromisoformat(dt_str)
                        if default_tz_name:
                            # Apply the specified timezone
                            if default_tz_name.upper() == 'UTC':
                                tz = timezone.utc
                            else:
                                tz = ZoneInfo(default_tz_name)
                            dt = dt.replace(tzinfo=tz)
                        else:
                            # Default to UTC
                            dt = dt.replace(tzinfo=timezone.utc)
                        
                        # Convert to UTC for internal processing
                        return dt.astimezone(timezone.utc)
                except Exception as e:
                    raise ValueError(f"Invalid datetime format: {dt_str}. Error: {e}")
            
            try:
                start_dt = parse_datetime_with_tz(start_time, tz)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid start_time format: {start_time}. Use ISO format like '2025-07-25T12:00:00Z' or '2025-07-25T12:00:00' with tz parameter. Error: {str(e)}"
                )
            
            # Parse end_time or calculate from duration
            if end_time:
                try:
                    end_dt = parse_datetime_with_tz(end_time, tz)
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid end_time format: {end_time}. Use ISO format like '2025-07-25T12:01:00Z' or '2025-07-25T12:01:00' with tz parameter. Error: {str(e)}"
                    )
            elif duration:
                # Parse duration (e.g., "1m", "5m", "1h", "2d")
                duration_pattern = re.match(r'^(\d+)([smhd])$', duration.lower())
                if not duration_pattern:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid duration format: {duration}. Use format like '1m', '5m', '1h', '2d'"
                    )
                
                amount, unit = duration_pattern.groups()
                amount = int(amount)
                
                if unit == 's':
                    delta = timedelta(seconds=amount)
                elif unit == 'm':
                    delta = timedelta(minutes=amount)
                elif unit == 'h':
                    delta = timedelta(hours=amount)
                elif unit == 'd':
                    delta = timedelta(days=amount)
                
                end_dt = start_dt + delta
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Either end_time or duration must be provided"
                )
            
            # Validate time range
            if end_dt <= start_dt:
                raise HTTPException(
                    status_code=400,
                    detail="end_time must be after start_time"
                )
            
            # Query the data using the existing storage query_range method
            if storage_type == "json":
                messages = await buffer_query.json_storage.query_range(
                    contract_id=contract_id,
                    tick_types=tick_type_list,
                    start_time=start_dt,
                    end_time=end_dt
                )
            elif storage_type == "protobuf":
                messages = await buffer_query.protobuf_storage.query_range(
                    contract_id=contract_id,
                    tick_types=tick_type_list,
                    start_time=start_dt,
                    end_time=end_dt
                )
            elif storage_type == "both":
                # Combine results from both storage types
                json_messages = await buffer_query.json_storage.query_range(
                    contract_id=contract_id,
                    tick_types=tick_type_list,
                    start_time=start_dt,
                    end_time=end_dt
                )
                proto_messages = await buffer_query.protobuf_storage.query_range(
                    contract_id=contract_id,
                    tick_types=tick_type_list,
                    start_time=start_dt,
                    end_time=end_dt
                )
                # Combine and sort by timestamp
                messages = json_messages + proto_messages
                messages.sort(key=lambda x: x.get('timestamp', ''))
            else:
                raise HTTPException(
                    status_code=400,
                    detail="storage_type must be 'json', 'protobuf', or 'both'"
                )
            
            # Apply limit if specified
            if limit and limit > 0:
                messages = messages[:limit]
            
            # Calculate actual time range of returned data
            actual_start = None
            actual_end = None
            if messages:
                timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
                if timestamps:
                    actual_start = min(timestamps)
                    actual_end = max(timestamps)
            
            return {
                "contract_id": contract_id,
                "tick_types": tick_type_list,
                "requested_range": {
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "duration_seconds": (end_dt - start_dt).total_seconds()
                },
                "actual_range": {
                    "start_time": actual_start,
                    "end_time": actual_end,
                    "message_count": len(messages)
                },
                "storage_type": storage_type,
                "messages": messages,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Buffer range query error: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            )
    
    @router.get("/v2/buffer/{contract_id}/range/stream")
    async def buffer_range_query_stream(
        contract_id: int,
        tick_types: str = Query(default="bid_ask,last", description="Comma-separated tick types"),
        start_time: str = Query(..., description="Start time in ISO format (e.g., 2025-07-25T12:00:00Z) or with timezone (e.g., 2025-07-25T12:00:00-05:00)"),
        end_time: str = Query(None, description="End time in ISO format (optional if duration provided)"),
        duration: str = Query(None, description="Duration from start_time (e.g., '1m', '5m', '1h')"),
        storage_type: str = Query(default="json", description="Storage type: json, protobuf, or both"),
        tz: str = Query(default=None, description="Timezone for interpreting start_time/end_time if no timezone specified (e.g., 'America/New_York', 'UTC')"),
        limit: Optional[int] = Query(default=None, description="Maximum number of messages to return")
    ):
        """Stream buffer data for a specific time range without loading all into memory"""
        from ..app_lifecycle import get_app_state
        from datetime import datetime, timezone, timedelta
        import re
        import json
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            # Fallback for Python < 3.9
            from backports.zoneinfo import ZoneInfo
        
        app_state = get_app_state()
        storage = app_state['storage']
        
        # Parse tick types
        tick_type_list = [t.strip() for t in tick_types.split(',')]
        
        # Check if storage is available
        if not storage:
            raise HTTPException(
                status_code=503,
                detail="Storage system not available"
            )
        
        try:
            buffer_query = create_buffer_query(config.storage.storage_base_path)
            
            # Check if contract has stored data
            if not buffer_query.is_contract_tracked(contract_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Contract {contract_id} has no stored data"
                )
            
            # Parse start_time with timezone support (reuse function from above)
            def parse_datetime_with_tz(dt_str: str, default_tz_name: str = None) -> datetime:
                """Parse datetime string with optional timezone support"""
                try:
                    if dt_str.endswith('Z'):
                        # UTC timezone
                        return datetime.fromisoformat(dt_str[:-1]).replace(tzinfo=timezone.utc)
                    elif '+' in dt_str[-6:] or dt_str[-6:-3] == '-':
                        # Has timezone offset (e.g., +05:00 or -04:00)
                        return datetime.fromisoformat(dt_str)
                    else:
                        # No timezone specified - use provided timezone or UTC
                        dt = datetime.fromisoformat(dt_str)
                        if default_tz_name:
                            # Apply the specified timezone
                            if default_tz_name.upper() == 'UTC':
                                tz = timezone.utc
                            else:
                                tz = ZoneInfo(default_tz_name)
                            dt = dt.replace(tzinfo=tz)
                        else:
                            # Default to UTC
                            dt = dt.replace(tzinfo=timezone.utc)
                        
                        # Convert to UTC for internal processing
                        return dt.astimezone(timezone.utc)
                except Exception as e:
                    raise ValueError(f"Invalid datetime format: {dt_str}. Error: {e}")
            
            try:
                start_dt = parse_datetime_with_tz(start_time, tz)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid start_time format: {start_time}. Use ISO format like '2025-07-25T12:00:00Z' or '2025-07-25T12:00:00' with tz parameter. Error: {str(e)}"
                )
            
            # Parse end_time or calculate from duration
            if end_time:
                try:
                    end_dt = parse_datetime_with_tz(end_time, tz)
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid end_time format: {end_time}. Use ISO format like '2025-07-25T12:01:00Z' or '2025-07-25T12:01:00' with tz parameter. Error: {str(e)}"
                    )
            elif duration:
                # Parse duration (e.g., "1m", "5m", "1h", "2d")
                duration_pattern = re.match(r'^(\d+)([smhd])$', duration.lower())
                if not duration_pattern:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid duration format: {duration}. Use format like '1m', '5m', '1h', '2d'"
                    )
                
                amount, unit = duration_pattern.groups()
                amount = int(amount)
                
                if unit == 's':
                    delta = timedelta(seconds=amount)
                elif unit == 'm':
                    delta = timedelta(minutes=amount)
                elif unit == 'h':
                    delta = timedelta(hours=amount)
                elif unit == 'd':
                    delta = timedelta(days=amount)
                
                end_dt = start_dt + delta
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Either end_time or duration must be provided"
                )
            
            # Validate time range
            if end_dt <= start_dt:
                raise HTTPException(
                    status_code=400,
                    detail="end_time must be after start_time"
                )
            
            # Stream the data using the new streaming query method
            async def generate_stream():
                # Send initial header
                yield f"data: {json.dumps({'_header': True, 'contract_id': contract_id, 'tick_types': tick_type_list, 'requested_range': {'start_time': start_dt.isoformat(), 'end_time': end_dt.isoformat(), 'duration_seconds': (end_dt - start_dt).total_seconds()}, 'storage_type': storage_type, 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
                
                message_count = 0
                
                if storage_type == "json":
                    async for message in buffer_query.json_storage.query_range_stream(
                        contract_id=contract_id,
                        tick_types=tick_type_list,
                        start_time=start_dt,
                        end_time=end_dt
                    ):
                        if message.get('_summary'):
                            # Final summary message
                            yield f"data: {json.dumps(message)}\n\n"
                        else:
                            message_count += 1
                            if limit and message_count > limit:
                                # Send summary and stop
                                yield f"data: {json.dumps({'_summary': True, 'message_count': message_count - 1, 'limit_reached': True})}\n\n"
                                break
                            yield f"data: {json.dumps(message)}\n\n"
                else:
                    # For now, only support JSON streaming
                    yield f"data: {json.dumps({'_error': True, 'message': 'Streaming only supported for JSON storage currently'})}\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/plain; charset=utf-8"
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Buffer range stream query error: {str(e)}"
            )
    
    app.include_router(router)