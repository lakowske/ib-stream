"""
StreamManager and StreamHandler classes for isolated multi-stream support.

This module provides request-ID based stream isolation to prevent cross-contamination
between concurrent streams for different contracts.
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger(__name__)


class StreamHandler:
    """Isolated stream handler for each individual stream request."""
    
    def __init__(self, 
                 request_id: int,
                 contract_id: int, 
                 tick_type: str, 
                 limit: Optional[int] = None,
                 timeout: Optional[int] = None,
                 tick_callback: Optional[Callable] = None,
                 error_callback: Optional[Callable] = None,
                 complete_callback: Optional[Callable] = None):
        self.request_id = request_id
        self.contract_id = contract_id
        self.tick_type = tick_type
        self.limit = limit
        self.timeout = timeout
        self.tick_callback = tick_callback
        self.error_callback = error_callback
        self.complete_callback = complete_callback
        
        # Stream state (isolated per stream)
        self.tick_count = 0
        self.streaming_stopped = False
        self.start_time = time.time()
        self.contract_details = None
        
        logger.info("Created StreamHandler for request_id %d, contract %d, type %s", 
                   request_id, contract_id, tick_type)
    
    async def process_tick(self, tick_data: Dict[str, Any]):
        """Process incoming tick data for this specific stream."""
        if self.streaming_stopped:
            return
        
        self.tick_count += 1
        
        logger.debug("StreamHandler %d processing tick %d: %s", 
                    self.request_id, self.tick_count, tick_data)
        
        # Send tick to callback
        if self.tick_callback:
            try:
                if asyncio.iscoroutinefunction(self.tick_callback):
                    await self.tick_callback(tick_data)
                else:
                    self.tick_callback(tick_data)
            except Exception as e:
                logger.error("Error in tick callback for request %d: %s", self.request_id, e)
        
        # Check if we've reached the limit
        if self.limit and self.tick_count >= self.limit:
            await self._complete_stream("limit_reached")
        
        # Check timeout
        elif self.timeout and (time.time() - self.start_time) >= self.timeout:
            await self._complete_stream("timeout")
    
    async def process_error(self, error_code: str, error_message: str):
        """Process error for this specific stream."""
        logger.warning("StreamHandler %d received error %s: %s", 
                      self.request_id, error_code, error_message)
        
        if self.error_callback:
            try:
                if asyncio.iscoroutinefunction(self.error_callback):
                    await self.error_callback(error_code, error_message)
                else:
                    self.error_callback(error_code, error_message)
            except Exception as e:
                logger.error("Error in error callback for request %d: %s", self.request_id, e)
    
    async def _complete_stream(self, reason: str):
        """Mark stream as complete and notify callback."""
        if self.streaming_stopped:
            return
            
        self.streaming_stopped = True
        
        logger.info("StreamHandler %d completed: %s, total_ticks=%d", 
                   self.request_id, reason, self.tick_count)
        
        if self.complete_callback:
            try:
                if asyncio.iscoroutinefunction(self.complete_callback):
                    await self.complete_callback(reason, self.tick_count)
                else:
                    self.complete_callback(reason, self.tick_count)
            except Exception as e:
                logger.error("Error in complete callback for request %d: %s", self.request_id, e)
    
    async def stop(self):
        """Manually stop this stream."""
        await self._complete_stream("manual_stop")
    
    def is_active(self) -> bool:
        """Check if stream is still active."""
        return not self.streaming_stopped
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stream statistics."""
        return {
            "request_id": self.request_id,
            "contract_id": self.contract_id, 
            "tick_type": self.tick_type,
            "tick_count": self.tick_count,
            "active": self.is_active(),
            "uptime_seconds": time.time() - self.start_time,
            "limit": self.limit,
            "timeout": self.timeout
        }


class StreamManager:
    """Central manager for routing tick data to correct stream handlers."""
    
    def __init__(self):
        self.stream_handlers: Dict[int, StreamHandler] = {}
        self.lock = threading.Lock()
        
        logger.info("StreamManager initialized")
    
    def register_stream(self, stream_handler: StreamHandler) -> None:
        """Register a new stream handler."""
        with self.lock:
            self.stream_handlers[stream_handler.request_id] = stream_handler
            logger.info("Registered stream handler for request_id %d (contract %d)", 
                       stream_handler.request_id, stream_handler.contract_id)
    
    def unregister_stream(self, request_id: int) -> None:
        """Unregister and clean up a stream handler."""
        with self.lock:
            if request_id in self.stream_handlers:
                handler = self.stream_handlers.pop(request_id)
                logger.info("Unregistered stream handler for request_id %d (contract %d)", 
                           request_id, handler.contract_id)
                return handler
            else:
                logger.warning("Attempted to unregister non-existent request_id %d", request_id)
                return None
    
    async def route_tick_data(self, request_id: int, tick_data: Dict[str, Any]) -> bool:
        """Route incoming tick data to the appropriate stream handler."""
        with self.lock:
            handler = self.stream_handlers.get(request_id)
        
        if handler:
            await handler.process_tick(tick_data)
            
            # If handler completed, remove it
            if not handler.is_active():
                self.unregister_stream(request_id)
            
            return True
        else:
            logger.debug("Received tick data for unknown request_id %d", request_id)
            return False
    
    async def route_error(self, request_id: int, error_code: str, error_message: str) -> bool:
        """Route error to the appropriate stream handler."""
        with self.lock:
            handler = self.stream_handlers.get(request_id)
        
        if handler:
            await handler.process_error(error_code, error_message)
            return True
        else:
            logger.warning("Received error for unknown request_id %d: %s", request_id, error_message)
            return False
    
    async def stop_stream(self, request_id: int) -> bool:
        """Stop a specific stream."""
        with self.lock:
            handler = self.stream_handlers.get(request_id)
        
        if handler:
            await handler.stop()
            self.unregister_stream(request_id)
            return True
        else:
            logger.warning("Attempted to stop non-existent request_id %d", request_id)
            return False
    
    async def stop_all_streams(self) -> int:
        """Stop all active streams."""
        with self.lock:
            handlers = list(self.stream_handlers.values())
            self.stream_handlers.clear()
        
        count = 0
        for handler in handlers:
            await handler.stop()
            count += 1
        
        logger.info("Stopped %d active streams", count)
        return count
    
    def get_active_streams(self) -> Dict[int, Dict[str, Any]]:
        """Get information about all active streams."""
        with self.lock:
            return {
                request_id: handler.get_stats() 
                for request_id, handler in self.stream_handlers.items()
                if handler.is_active()
            }
    
    def get_stream_count(self) -> int:
        """Get the number of active streams."""
        with self.lock:
            return len([h for h in self.stream_handlers.values() if h.is_active()])
    
    def cleanup_inactive_streams(self) -> int:
        """Remove inactive stream handlers."""
        with self.lock:
            inactive_ids = [
                request_id for request_id, handler in self.stream_handlers.items()
                if not handler.is_active()
            ]
            
            for request_id in inactive_ids:
                del self.stream_handlers[request_id]
        
        if inactive_ids:
            logger.info("Cleaned up %d inactive streams", len(inactive_ids))
        
        return len(inactive_ids)


# Global stream manager instance
stream_manager = StreamManager()