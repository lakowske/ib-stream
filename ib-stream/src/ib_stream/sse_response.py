"""
Server-Sent Events (SSE) response handler for streaming market data.
"""

import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class SSEEvent:
    """Represents a Server-Sent Event"""

    def __init__(self, event_type: str, data: Dict[str, Any], event_id: Optional[str] = None):
        self.event_type = event_type
        self.data = data
        self.event_id = event_id
        self.timestamp = datetime.now().isoformat()

    def format(self) -> str:
        """Format event as SSE string"""
        lines = []

        if self.event_id:
            lines.append(f"id: {self.event_id}")

        lines.append(f"event: {self.event_type}")

        # Add timestamp to data
        event_data = {
            "type": self.event_type,
            "timestamp": self.timestamp,
            **self.data
        }

        data_json = json.dumps(event_data, ensure_ascii=False)
        lines.append(f"data: {data_json}")

        lines.append("")  # Empty line to end the event
        return "\n".join(lines)


class SSETickEvent(SSEEvent):
    """SSE event for market data ticks"""

    def __init__(self, contract_id: int, tick_data: Dict[str, Any], event_id: Optional[str] = None):
        data = {
            "contract_id": contract_id,
            "data": tick_data
        }
        super().__init__("tick", data, event_id)


class SSEErrorEvent(SSEEvent):
    """SSE event for errors"""

    def __init__(self, contract_id: int, error_code: str, message: str,
                 details: Optional[str] = None, event_id: Optional[str] = None):
        data = {
            "contract_id": contract_id,
            "error": {
                "code": error_code,
                "message": message,
                "details": details
            }
        }
        super().__init__("error", data, event_id)


class SSECompleteEvent(SSEEvent):
    """SSE event for stream completion"""

    def __init__(self, contract_id: int, reason: str, total_ticks: int,
                 event_id: Optional[str] = None):
        data = {
            "contract_id": contract_id,
            "reason": reason,
            "total_ticks": total_ticks
        }
        super().__init__("complete", data, event_id)


class SSEInfoEvent(SSEEvent):
    """SSE event for stream information"""

    def __init__(self, contract_id: int, info: Dict[str, Any], event_id: Optional[str] = None):
        data = {
            "contract_id": contract_id,
            "info": info
        }
        super().__init__("info", data, event_id)


class SSEStreamingResponse(StreamingResponse):
    """Custom streaming response for SSE"""

    def __init__(self, content: AsyncGenerator[str, None], **kwargs):
        # Set proper SSE headers
        headers = kwargs.get("headers", {})
        headers.update({
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        })
        kwargs["headers"] = headers

        super().__init__(content, **kwargs)


async def create_sse_generator(events: AsyncGenerator[SSEEvent, None]) -> AsyncGenerator[str, None]:
    """Convert SSE events to formatted strings"""
    try:
        async for event in events:
            yield event.format()
    except Exception as e:
        logger.error("Error in SSE generator: %s", e)
        # Send error event
        error_event = SSEErrorEvent(
            contract_id=0,
            error_code="STREAM_ERROR",
            message=f"Stream error: {str(e)}"
        )
        yield error_event.format()


def create_sse_response(events: AsyncGenerator[SSEEvent, None]) -> SSEStreamingResponse:
    """Create SSE streaming response from events"""
    return SSEStreamingResponse(
        content=create_sse_generator(events),
        media_type="text/event-stream"
    )


def create_heartbeat_event() -> SSEEvent:
    """Create a heartbeat event to keep connection alive"""
    return SSEEvent("heartbeat", {"message": "heartbeat"})


def create_stream_started_event(contract_id: int, tick_type: str,
                               contract_info: Optional[Dict[str, Any]] = None) -> SSEInfoEvent:
    """Create event to signal stream start"""
    info = {
        "message": "Stream started",
        "tick_type": tick_type,
        "contract_info": contract_info
    }
    return SSEInfoEvent(contract_id, info)


def create_connection_error_event(contract_id: int, error_message: str) -> SSEErrorEvent:
    """Create event for connection errors"""
    return SSEErrorEvent(
        contract_id=contract_id,
        error_code="CONNECTION_ERROR",
        message=error_message,
        details="Check TWS connection and try again"
    )


def create_contract_not_found_event(contract_id: int) -> SSEErrorEvent:
    """Create event for contract not found errors"""
    return SSEErrorEvent(
        contract_id=contract_id,
        error_code="CONTRACT_NOT_FOUND",
        message=f"Could not find contract with ID {contract_id}",
        details="Verify contract ID using the contract lookup API"
    )


def create_rate_limit_error_event(contract_id: int) -> SSEErrorEvent:
    """Create event for rate limit errors"""
    return SSEErrorEvent(
        contract_id=contract_id,
        error_code="RATE_LIMIT_EXCEEDED",
        message="Too many concurrent streams",
        details="Try again later or reduce concurrent connections"
    )


def create_timeout_error_event(contract_id: int, timeout_seconds: int) -> SSEErrorEvent:
    """Create event for timeout errors"""
    return SSEErrorEvent(
        contract_id=contract_id,
        error_code="STREAM_TIMEOUT",
        message=f"Stream timeout after {timeout_seconds} seconds",
        details="Stream automatically terminated due to timeout"
    )
