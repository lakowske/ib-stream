"""Server-Sent Events (SSE) response handler for IB-Stream v2 protocol."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi.responses import StreamingResponse

from .protocol_types import (
    V2Message,
    TickMessage,
    ErrorMessage,
    CompleteMessage,
    InfoMessage
)

logger = logging.getLogger(__name__)


class SSEEvent:
    """Represents a Server-Sent Event in v2 protocol format."""

    def __init__(self, message: V2Message, event_id: Optional[str] = None):
        self.message = message
        self.event_id = event_id

    def format(self) -> str:
        """Format event as SSE string following v2 protocol."""
        lines = []

        if self.event_id:
            lines.append(f"id: {self.event_id}")

        # Event field matches message type
        lines.append(f"event: {self.message.type}")

        # Data contains the full v2 message
        data_json = self.message.to_json()
        lines.append(f"data: {data_json}")

        lines.append("")  # Empty line to end the event
        return "\n".join(lines)


def create_tick_event(stream_id: str, contract_id: int, tick_type: str, tick_data: Dict[str, Any]) -> SSEEvent:
    """Create SSE tick event with v2 protocol structure."""
    message = TickMessage(stream_id, contract_id, tick_type, tick_data)
    return SSEEvent(message)


def create_error_event(stream_id: str, code: str, message: str, details: Optional[Dict[str, Any]] = None, recoverable: bool = True) -> SSEEvent:
    """Create SSE error event with v2 protocol structure."""
    error_msg = ErrorMessage(stream_id, code, message, details, recoverable)
    return SSEEvent(error_msg)


def create_complete_event(stream_id: str, reason: str, total_ticks: int, duration_seconds: float, final_sequence: Optional[int] = None) -> SSEEvent:
    """Create SSE completion event with v2 protocol structure."""
    complete_msg = CompleteMessage(stream_id, reason, total_ticks, duration_seconds, final_sequence)
    return SSEEvent(complete_msg)


def create_info_event(stream_id: str, status: str, contract_info: Optional[Dict[str, Any]] = None, stream_config: Optional[Dict[str, Any]] = None) -> SSEEvent:
    """Create SSE info event with v2 protocol structure."""
    info_msg = InfoMessage(stream_id, status, contract_info, stream_config)
    return SSEEvent(info_msg)


class SSEStreamingResponse(StreamingResponse):
    """Custom streaming response for SSE with v2 protocol headers."""

    def __init__(self, content: AsyncGenerator[str, None], **kwargs):
        # Set proper SSE headers with v2 version
        headers = kwargs.get("headers", {})
        headers.update({
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "X-IB-Stream-Version": "2.0.0",
        })
        kwargs["headers"] = headers

        super().__init__(content, **kwargs)


async def create_sse_generator(events: AsyncGenerator[SSEEvent, None]) -> AsyncGenerator[str, None]:
    """Convert SSE events to formatted strings."""
    try:
        async for event in events:
            yield event.format()
    except Exception as e:
        logger.error("Error in SSE generator: %s", e)
        # Send error event with empty stream_id (connection-level error)
        error_event = create_error_event("", "STREAM_ERROR", f"Stream error: {str(e)}")
        yield error_event.format()


def create_sse_response(events: AsyncGenerator[SSEEvent, None]) -> SSEStreamingResponse:
    """Create SSE streaming response from events."""
    return SSEStreamingResponse(
        content=create_sse_generator(events),
        media_type="text/event-stream"
    )


def create_heartbeat_event() -> SSEEvent:
    """Create a heartbeat event to keep connection alive."""
    from .protocol_types import V2Message
    heartbeat_msg = V2Message("heartbeat", "", {"message": "heartbeat"})
    return SSEEvent(heartbeat_msg)


def create_stream_started_event(stream_id: str, tick_type: str, contract_info: Optional[Dict[str, Any]] = None) -> SSEEvent:
    """Create event to signal stream start."""
    stream_config = {
        "tick_type": tick_type,
        "contract_info": contract_info
    }
    return create_info_event(stream_id, "subscribed", contract_info, stream_config)


def create_connection_error_event(stream_id: str, error_message: str) -> SSEEvent:
    """Create event for connection errors."""
    return create_error_event(
        stream_id,
        "CONNECTION_ERROR",
        error_message,
        {"suggestion": "Check TWS connection and try again"},
        recoverable=True
    )


def create_contract_not_found_event(stream_id: str, contract_id: int) -> SSEEvent:
    """Create event for contract not found errors."""
    return create_error_event(
        stream_id,
        "CONTRACT_NOT_FOUND",
        f"Could not find contract with ID {contract_id}",
        {
            "contract_id": contract_id,
            "suggestion": "Verify contract ID using the contract lookup API"
        },
        recoverable=False
    )


def create_rate_limit_error_event(stream_id: str) -> SSEEvent:
    """Create event for rate limit errors."""
    return create_error_event(
        stream_id,
        "RATE_LIMIT_EXCEEDED",
        "Too many concurrent streams",
        {"suggestion": "Try again later or reduce concurrent connections"},
        recoverable=True
    )


def create_timeout_error_event(stream_id: str, timeout_seconds: int) -> SSEEvent:
    """Create event for timeout errors."""
    return create_error_event(
        stream_id,
        "STREAM_TIMEOUT",
        f"Stream timeout after {timeout_seconds} seconds",
        {"suggestion": "Stream automatically terminated due to timeout"},
        recoverable=True
    )