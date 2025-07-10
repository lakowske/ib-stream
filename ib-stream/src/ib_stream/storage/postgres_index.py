"""
PostgreSQL indexing for IB Stream storage.

Provides metadata indexing and file tracking for efficient
historical data queries.
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class PostgreSQLIndex:
    """
    PostgreSQL-based metadata index for storage files.
    
    Tracks file locations, time ranges, and statistics for
    efficient query planning and data discovery.
    """
    
    def __init__(
        self,
        connection_url: str,
        schema_name: str = "ib_stream_storage"
    ):
        """
        Initialize PostgreSQL index.
        
        Args:
            connection_url: PostgreSQL connection URL
            schema_name: Schema name for storage tables
        """
        self.connection_url = connection_url
        self.schema_name = schema_name
        self.pool: Optional[asyncpg.Pool] = None
        
    async def start(self):
        """Initialize database connection and create schema."""
        try:
            # Create connection pool
            self.pool = await asyncpg.create_pool(
                self.connection_url,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            
            # Create schema and tables
            await self._create_schema()
            
            logger.info("PostgreSQL storage index initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL index: {e}")
            raise
            
    async def stop(self):
        """Close database connections."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            
        logger.info("PostgreSQL storage index stopped")
        
    async def _create_schema(self):
        """Create database schema and tables."""
        async with self.pool.acquire() as conn:
            # Create schema
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema_name}")
            
            # Create file tracking table
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.storage_files (
                    id SERIAL PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    contract_id INTEGER NOT NULL,
                    tick_type TEXT NOT NULL,
                    storage_format TEXT NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    start_time TIMESTAMPTZ NOT NULL,
                    end_time TIMESTAMPTZ NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    file_size_bytes BIGINT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # Create indexes for efficient queries
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_storage_files_contract_time 
                ON {self.schema_name}.storage_files (contract_id, tick_type, start_time, end_time)
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_storage_files_time_range 
                ON {self.schema_name}.storage_files USING GIST (
                    tstzrange(start_time, end_time, '[]')
                )
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_storage_files_stream_id 
                ON {self.schema_name}.storage_files (stream_id)
            """)
            
            # Create daily statistics table
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.daily_statistics (
                    contract_id INTEGER NOT NULL,
                    tick_type TEXT NOT NULL,
                    date DATE NOT NULL,
                    total_messages BIGINT DEFAULT 0,
                    unique_prices INTEGER DEFAULT 0,
                    total_volume DECIMAL DEFAULT 0,
                    vwap DECIMAL DEFAULT 0,
                    high_price DECIMAL DEFAULT 0,
                    low_price DECIMAL DEFAULT 0,
                    first_message_time TIMESTAMPTZ,
                    last_message_time TIMESTAMPTZ,
                    file_count INTEGER DEFAULT 0,
                    total_file_size BIGINT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    
                    PRIMARY KEY (contract_id, tick_type, date)
                )
            """)
            
            # Create storage health table
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.storage_health (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    backend TEXT NOT NULL,
                    messages_written BIGINT DEFAULT 0,
                    messages_errored BIGINT DEFAULT 0,
                    avg_write_time_ms DECIMAL DEFAULT 0,
                    queue_size INTEGER DEFAULT 0,
                    health_score DECIMAL DEFAULT 100.0,
                    details JSONB
                )
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_storage_health_timestamp 
                ON {self.schema_name}.storage_health (timestamp DESC)
            """)
            
    async def register_file(
        self,
        stream_id: str,
        contract_id: int,
        tick_type: str,
        storage_format: str,
        file_path: Path,
        start_time: datetime,
        end_time: datetime,
        message_count: int = 0,
        file_size: int = 0
    ) -> int:
        """
        Register a new storage file in the index.
        
        Args:
            stream_id: Stream identifier
            contract_id: Contract ID
            tick_type: Type of tick data
            storage_format: Storage format (json, protobuf)
            file_path: Path to the storage file
            start_time: First message timestamp
            end_time: Last message timestamp
            message_count: Number of messages in file
            file_size: File size in bytes
            
        Returns:
            File record ID
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                INSERT INTO {self.schema_name}.storage_files (
                    stream_id, contract_id, tick_type, storage_format,
                    file_path, start_time, end_time, message_count, file_size_bytes
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (file_path) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    message_count = EXCLUDED.message_count,
                    file_size_bytes = EXCLUDED.file_size_bytes,
                    updated_at = NOW()
                RETURNING id
            """, stream_id, contract_id, tick_type, storage_format,
                str(file_path), start_time, end_time, message_count, file_size)
            
            file_id = row['id']
            
            # Update daily statistics
            await self._update_daily_stats(
                contract_id, tick_type, start_time.date(),
                message_count, file_size
            )
            
            logger.debug(f"Registered storage file: {file_path} (ID: {file_id})")
            return file_id
            
    async def find_files_for_range(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: datetime,
        storage_format: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find storage files that contain data for the specified range.
        
        Args:
            contract_id: Contract ID to search for
            tick_types: List of tick types to include
            start_time: Start of time range
            end_time: End of time range
            storage_format: Storage format filter (optional)
            
        Returns:
            List of file records
        """
        conditions = [
            "contract_id = $1",
            "tick_type = ANY($2)",
            "tstzrange(start_time, end_time, '[]') && tstzrange($3, $4, '[]')"
        ]
        params = [contract_id, tick_types, start_time, end_time]
        
        if storage_format:
            conditions.append(f"storage_format = ${len(params) + 1}")
            params.append(storage_format)
            
        query = f"""
            SELECT id, stream_id, contract_id, tick_type, storage_format,
                   file_path, start_time, end_time, message_count, file_size_bytes
            FROM {self.schema_name}.storage_files
            WHERE {' AND '.join(conditions)}
            ORDER BY start_time
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
        return [dict(row) for row in rows]
        
    async def get_daily_statistics(
        self,
        contract_id: int,
        tick_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily statistics for a contract and tick type.
        
        Args:
            contract_id: Contract ID
            tick_type: Tick type
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            List of daily statistics
        """
        conditions = ["contract_id = $1", "tick_type = $2"]
        params = [contract_id, tick_type]
        
        if start_date:
            conditions.append(f"date >= ${len(params) + 1}")
            params.append(start_date.date())
            
        if end_date:
            conditions.append(f"date <= ${len(params) + 1}")
            params.append(end_date.date())
            
        query = f"""
            SELECT contract_id, tick_type, date, total_messages, unique_prices,
                   total_volume, vwap, high_price, low_price,
                   first_message_time, last_message_time, file_count, total_file_size
            FROM {self.schema_name}.daily_statistics
            WHERE {' AND '.join(conditions)}
            ORDER BY date
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
        return [dict(row) for row in rows]
        
    async def _update_daily_stats(
        self,
        contract_id: int,
        tick_type: str,
        date: datetime.date,
        message_count: int,
        file_size: int
    ):
        """Update daily statistics with new file data."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self.schema_name}.daily_statistics (
                    contract_id, tick_type, date, total_messages, file_count, total_file_size
                ) VALUES ($1, $2, $3, $4, 1, $5)
                ON CONFLICT (contract_id, tick_type, date) DO UPDATE SET
                    total_messages = daily_statistics.total_messages + EXCLUDED.total_messages,
                    file_count = daily_statistics.file_count + 1,
                    total_file_size = daily_statistics.total_file_size + EXCLUDED.total_file_size,
                    updated_at = NOW()
            """, contract_id, tick_type, date, message_count, file_size)
            
    async def record_health_metrics(
        self,
        backend: str,
        metrics: Dict[str, Any]
    ):
        """
        Record storage health metrics.
        
        Args:
            backend: Storage backend name
            metrics: Health metrics dictionary
        """
        async with self.pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self.schema_name}.storage_health (
                    backend, messages_written, messages_errored, 
                    avg_write_time_ms, queue_size, health_score, details
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
                backend,
                metrics.get('messages_written', 0),
                metrics.get('messages_errored', 0),
                metrics.get('avg_write_time_ms', 0),
                metrics.get('queue_size', 0),
                metrics.get('health_score', 100.0),
                metrics
            )
            
    async def get_storage_overview(self) -> Dict[str, Any]:
        """
        Get an overview of storage statistics.
        
        Returns:
            Storage overview with key metrics
        """
        async with self.pool.acquire() as conn:
            # File statistics
            file_stats = await conn.fetchrow(f"""
                SELECT 
                    COUNT(*) as total_files,
                    COUNT(DISTINCT contract_id) as unique_contracts,
                    COUNT(DISTINCT tick_type) as unique_tick_types,
                    SUM(message_count) as total_messages,
                    SUM(file_size_bytes) as total_bytes,
                    MIN(start_time) as earliest_data,
                    MAX(end_time) as latest_data
                FROM {self.schema_name}.storage_files
            """)
            
            # Recent activity
            recent_files = await conn.fetchrow(f"""
                SELECT COUNT(*) as files_last_24h
                FROM {self.schema_name}.storage_files
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            # Top contracts by data volume
            top_contracts = await conn.fetch(f"""
                SELECT 
                    contract_id,
                    COUNT(*) as file_count,
                    SUM(message_count) as total_messages,
                    SUM(file_size_bytes) as total_bytes
                FROM {self.schema_name}.storage_files
                GROUP BY contract_id
                ORDER BY total_messages DESC
                LIMIT 10
            """)
            
            return {
                'overview': dict(file_stats) if file_stats else {},
                'recent_activity': dict(recent_files) if recent_files else {},
                'top_contracts': [dict(row) for row in top_contracts]
            }
            
    async def cleanup_old_health_records(self, days_to_keep: int = 7):
        """
        Clean up old health records to prevent table growth.
        
        Args:
            days_to_keep: Number of days of health records to keep
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(f"""
                DELETE FROM {self.schema_name}.storage_health
                WHERE timestamp < NOW() - INTERVAL '{days_to_keep} days'
            """)
            
            deleted_count = int(result.split()[-1])
            logger.info(f"Cleaned up {deleted_count} old health records")
            
    async def get_query_plan(
        self,
        contract_id: int,
        tick_types: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Generate an optimized query plan for data retrieval.
        
        Args:
            contract_id: Contract ID
            tick_types: List of tick types
            start_time: Start time
            end_time: End time
            
        Returns:
            Query plan with file list and estimated costs
        """
        files = await self.find_files_for_range(
            contract_id, tick_types, start_time, end_time
        )
        
        total_messages = sum(f.get('message_count', 0) for f in files)
        total_bytes = sum(f.get('file_size_bytes', 0) for f in files)
        
        # Group files by storage format
        files_by_format = {}
        for file_record in files:
            fmt = file_record['storage_format']
            if fmt not in files_by_format:
                files_by_format[fmt] = []
            files_by_format[fmt].append(file_record)
            
        return {
            'total_files': len(files),
            'total_messages': total_messages,
            'total_bytes': total_bytes,
            'estimated_read_time_seconds': total_bytes / (50 * 1024 * 1024),  # Assume 50MB/s read speed
            'files_by_format': files_by_format,
            'recommendation': 'protobuf' if 'protobuf' in files_by_format else 'json'
        }