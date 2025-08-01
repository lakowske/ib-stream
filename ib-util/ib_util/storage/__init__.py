"""
Storage module for optimized v3 tick message format.

This module provides the foundation for the optimized storage format that reduces
storage size by 50%+ while maintaining full data fidelity.
"""

from .tick_message import TickMessage, generate_request_id, create_tick_message_from_v2
from .v3_storage import V3StorageBase

__all__ = ['TickMessage', 'generate_request_id', 'create_tick_message_from_v2', 'V3StorageBase']