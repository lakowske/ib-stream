"""Multi-stream study runner for studies that require multiple concurrent streams."""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import List, Optional

from ib_studies.models import StreamConfig
from ib_studies.multi_stream_client import MultiStreamClient

logger = logging.getLogger(__name__)


class MultiStudyRunner:
    """Manages running studies with multiple concurrent stream connections."""
    
    def __init__(self, study, formatter, stream_config: StreamConfig):
        """Initialize multi-stream study runner."""
        self.study = study
        self.formatter = formatter
        self.stream_config = stream_config
        self.stream_client = None
        self.running = False
        self._stop_event = asyncio.Event()
        
    async def run(self, contract_id: int, tick_types: Optional[List[str]] = None) -> None:
        """Run the study with multiple concurrent streams."""
        self.running = True
        
        # Setup aggressive signal handlers for immediate termination
        def signal_handler():
            logger.info("Received interrupt signal, stopping all streams immediately...")
            self._stop_event.set()
            
            # Force disconnect all streams
            if self.stream_client:
                logger.info("Force stopping stream client...")
                # Create a task to force cleanup
                asyncio.create_task(self._force_cleanup())
        
        def emergency_exit(sig, frame):
            logger.error("Emergency exit - forcing immediate shutdown")
            if self.stream_client:
                # Try to cleanup synchronously
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Cancel all tasks and exit
                        for task in asyncio.all_tasks():
                            task.cancel()
                except:
                    pass
            sys.exit(1)
        
        # For Windows compatibility
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            # Add emergency handler for double Ctrl+C
            signal.signal(signal.SIGQUIT, emergency_exit)
        else:
            # Windows doesn't support signal handlers in event loops
            signal.signal(signal.SIGINT, lambda s, f: signal_handler())
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
        
        try:
            # Create and setup multi-stream client
            self.stream_client = MultiStreamClient(self.stream_config)
            
            # Use provided tick types or fall back to study's required types
            stream_tick_types = tick_types or self.study.required_tick_types
            logger.info("Starting multi-stream study with tick types: %s", stream_tick_types)
            
            # Show header
            if hasattr(self.formatter, 'format_header'):
                header = self.formatter.format_header(
                    contract_id, 
                    self.study.name,
                    window_seconds=self.study.config.window_seconds,
                    timestamp=self.study._start_time.isoformat()
                )
                self.formatter.output(header)
            
            # Connect to all streams
            await self.stream_client.connect_multiple(
                contract_id, 
                stream_tick_types, 
                self._handle_tick
            )
            
            # Wait for completion or stop signal
            try:
                await self.stream_client.wait_for_completion()
            except asyncio.CancelledError:
                logger.info("Study runner cancelled")
                raise
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            self._stop_event.set()
            if self.stream_client:
                await self.stream_client.stop()
        except asyncio.CancelledError:
            logger.info("Study runner task cancelled")
        except Exception as e:
            logger.error("Error running multi-stream study: %s", e, exc_info=True)
            if hasattr(self.formatter, 'format_error'):
                error_msg = self.formatter.format_error(str(e))
                self.formatter.output(error_msg)
        finally:
            await self.cleanup()
    
    async def _handle_tick(self, tick_type: str, data: dict) -> None:
        """Handle incoming tick data from any stream."""
        if self._stop_event.is_set():
            return
        
        logger.debug("MultiStudyRunner._handle_tick: tick_type=%s, data=%s", tick_type, data)
        
        try:
            # Process tick through study
            result = self.study.process_tick(tick_type, data)
            logger.debug("Study result: %s", result)
            
            # Format and output result (only for trade results, not quote updates)
            if result:
                logger.debug("Formatting output for result: %s", result)
                output = self.formatter.format_update(result)
                self.formatter.output(output)
            else:
                logger.debug("No result from study, skipping output")
                
        except Exception as e:
            logger.error("Error processing tick: %s", e, exc_info=True)
    
    async def _force_cleanup(self) -> None:
        """Force immediate cleanup of all resources."""
        logger.info("Force cleanup initiated")
        try:
            if self.stream_client:
                # Set stop event and disconnect immediately
                await self.stream_client.stop()
                await asyncio.wait_for(self.stream_client.disconnect_all(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("Force cleanup timed out, proceeding anyway")
        except Exception as e:
            logger.error("Error in force cleanup: %s", e)
        finally:
            # Exit after cleanup attempt
            logger.info("Force cleanup complete, exiting...")
            sys.exit(0)
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        self.running = False
        
        # Show final summary
        if hasattr(self.formatter, 'format_final_summary'):
            summary = self.study.get_summary()
            final_output = self.formatter.format_final_summary({"summary": summary})
            self.formatter.output(final_output)
        
        # Disconnect stream client
        if self.stream_client:
            await self.stream_client.disconnect_all()
        
        # Close formatter
        if hasattr(self.formatter, 'close'):
            self.formatter.close()