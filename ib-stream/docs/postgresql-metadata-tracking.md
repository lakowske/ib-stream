# PostgreSQL Metadata Tracking System Design

## Overview

This document describes a PostgreSQL-based metadata tracking system that eliminates the need for complex storage directory merging during production migrations. Instead of physically merging storage directories, the system tracks when and where each server instance was collecting data, allowing for complete timeline reconstruction through database queries.

## Core Concept

The system tracks metadata about data collection sessions rather than the data itself. This approach provides:

1. **Complete Timeline Reconstruction**: Query which server was collecting data at any given time
2. **No Storage Merging**: Keep storage directories separate, use database to coordinate access
3. **Migration Safety**: Track handoff events and validate data continuity
4. **Audit Trail**: Full history of server deployments and data collection periods

## Database Schema

### 1. Server Instances Table

Tracks each deployment/version of the IB Stream server:

```sql
CREATE TABLE server_instances (
    id SERIAL PRIMARY KEY,
    instance_name VARCHAR(100) NOT NULL,  -- e.g., 'production-v1.2.3', 'staging-feature-xyz'
    server_version VARCHAR(50) NOT NULL,  -- e.g., 'v1.2.3', 'feature-xyz-abc123'
    host VARCHAR(255) NOT NULL,           -- hostname/IP where server runs
    port INTEGER NOT NULL,                -- API port (8001, 8101, etc.)
    storage_path TEXT NOT NULL,           -- absolute path to storage directory
    environment VARCHAR(50) NOT NULL,     -- 'production', 'staging', 'development'
    tws_client_id INTEGER NOT NULL,       -- TWS client ID used
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(instance_name),
    UNIQUE(host, port)
);
```

### 2. Collection Sessions Table

Tracks active data collection periods for each server instance:

```sql
CREATE TABLE collection_sessions (
    id SERIAL PRIMARY KEY,
    server_instance_id INTEGER NOT NULL REFERENCES server_instances(id),
    session_start TIMESTAMP WITH TIME ZONE NOT NULL,
    session_end TIMESTAMP WITH TIME ZONE,     -- NULL for active sessions
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'terminated', 'failed'
    
    -- Configuration snapshot
    config_snapshot JSONB,                    -- Store relevant config at session start
    
    -- Performance metrics
    total_messages_collected BIGINT DEFAULT 0,
    total_storage_bytes BIGINT DEFAULT 0,
    
    -- Session metadata
    termination_reason VARCHAR(255),          -- Why session ended
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_session_status CHECK (status IN ('active', 'completed', 'terminated', 'failed'))
);
```

### 3. Session Contracts Table

Tracks which contracts were being collected during each session:

```sql
CREATE TABLE session_contracts (
    id SERIAL PRIMARY KEY,
    collection_session_id INTEGER NOT NULL REFERENCES collection_sessions(id),
    contract_id INTEGER NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    tick_types TEXT[] NOT NULL,             -- Array of tick types being collected
    
    -- Collection metrics per contract
    messages_collected BIGINT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    first_message_time TIMESTAMP WITH TIME ZONE,
    last_message_time TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(collection_session_id, contract_id)
);
```

### 4. Migration Events Table

Records migration events and handoffs between servers:

```sql
CREATE TABLE migration_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,        -- 'preparation', 'handoff', 'validation', 'rollback'
    event_status VARCHAR(20) NOT NULL,      -- 'started', 'completed', 'failed'
    
    -- Server instances involved
    source_server_id INTEGER REFERENCES server_instances(id),      -- Old server
    target_server_id INTEGER REFERENCES server_instances(id),      -- New server
    
    -- Timing
    event_start TIMESTAMP WITH TIME ZONE NOT NULL,
    event_end TIMESTAMP WITH TIME ZONE,
    
    -- Migration details
    migration_type VARCHAR(50) NOT NULL,    -- 'blue_green', 'rolling', 'maintenance'
    contracts_migrated INTEGER[],           -- Array of contract IDs being migrated
    
    -- Validation results
    validation_results JSONB,               -- Store validation checks and results
    
    -- Notes and metadata
    notes TEXT,
    metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_event_type CHECK (event_type IN ('preparation', 'handoff', 'validation', 'rollback')),
    CONSTRAINT valid_event_status CHECK (event_status IN ('started', 'completed', 'failed'))
);
```

## Data Reconstruction Algorithm

### Query: Find Server for Time Range

To reconstruct data for a specific time range, query which server was collecting data:

```sql
-- Find which server was collecting contract 711280073 at specific time
SELECT 
    si.instance_name,
    si.storage_path,
    si.host,
    si.port,
    cs.session_start,
    cs.session_end,
    sc.tick_types
FROM collection_sessions cs
JOIN server_instances si ON cs.server_instance_id = si.id
JOIN session_contracts sc ON cs.id = sc.collection_session_id
WHERE sc.contract_id = 711280073
  AND cs.session_start <= '2025-07-11 15:30:00+00'
  AND (cs.session_end IS NULL OR cs.session_end >= '2025-07-11 15:30:00+00')
  AND cs.status = 'active';
```

### Query: Timeline Reconstruction

For complete timeline reconstruction across multiple servers:

```sql
-- Get complete timeline for contract across all servers
SELECT 
    si.instance_name,
    si.storage_path,
    cs.session_start,
    cs.session_end,
    sc.tick_types,
    sc.messages_collected,
    -- Calculate time coverage
    CASE 
        WHEN cs.session_end IS NULL THEN 'ongoing'
        ELSE (cs.session_end - cs.session_start)::TEXT
    END as duration
FROM collection_sessions cs
JOIN server_instances si ON cs.server_instance_id = si.id
JOIN session_contracts sc ON cs.id = sc.collection_session_id
WHERE sc.contract_id = 711280073
  AND cs.session_start >= '2025-07-01 00:00:00+00'
  AND cs.session_start <= '2025-07-31 23:59:59+00'
ORDER BY cs.session_start;
```

### Query: Gap Detection

Detect gaps in data collection:

```sql
-- Find gaps in data collection for a contract
WITH session_timeline AS (
    SELECT 
        cs.session_start,
        cs.session_end,
        si.instance_name,
        LAG(cs.session_end) OVER (ORDER BY cs.session_start) as prev_session_end
    FROM collection_sessions cs
    JOIN server_instances si ON cs.server_instance_id = si.id  
    JOIN session_contracts sc ON cs.id = sc.collection_session_id
    WHERE sc.contract_id = 711280073
      AND cs.session_start >= '2025-07-01 00:00:00+00'
    ORDER BY cs.session_start
)
SELECT 
    prev_session_end as gap_start,
    session_start as gap_end,
    (session_start - prev_session_end) as gap_duration
FROM session_timeline 
WHERE prev_session_end IS NOT NULL 
  AND session_start > prev_session_end;
```

## Integration Points

### 1. Background Stream Manager Integration

Update `BackgroundStreamManager` to register sessions:

```python
class BackgroundStreamManager:
    def __init__(self, storage_manager, db_connection):
        self.storage_manager = storage_manager
        self.db_connection = db_connection
        self.session_id = None
        
    async def start_background_streams(self):
        """Start background streaming and register session."""
        # Register server instance if not exists
        await self._register_server_instance()
        
        # Start new collection session
        self.session_id = await self._start_collection_session()
        
        # Register tracked contracts
        await self._register_session_contracts()
        
        # Start actual streaming
        await self._start_streams()
        
    async def _register_server_instance(self):
        """Register this server instance in database."""
        await self.db_connection.execute("""
            INSERT INTO server_instances 
            (instance_name, server_version, host, port, storage_path, environment, tws_client_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (instance_name) DO UPDATE SET
                updated_at = NOW()
        """, [
            self.config.instance_name,
            self.config.server_version,  
            self.config.host,
            self.config.port,
            str(self.config.storage_path),
            self.config.environment,
            self.config.tws_client_id
        ])
        
    async def _start_collection_session(self) -> int:
        """Start new collection session."""
        session_id = await self.db_connection.fetchval("""
            INSERT INTO collection_sessions 
            (server_instance_id, session_start, config_snapshot)
            VALUES (
                (SELECT id FROM server_instances WHERE instance_name = $1),
                NOW(),
                $2
            )
            RETURNING id
        """, [
            self.config.instance_name,
            json.dumps(self.config.to_dict())
        ])
        return session_id
        
    async def _register_session_contracts(self):
        """Register contracts being collected in this session."""
        for contract_id, config in self.tracked_contracts.items():
            await self.db_connection.execute("""
                INSERT INTO session_contracts 
                (collection_session_id, contract_id, symbol, tick_types)
                VALUES ($1, $2, $3, $4)
            """, [
                self.session_id,
                contract_id,
                config.symbol,
                config.tick_types
            ])
```

### 2. Buffer Query Integration

Update `BufferQuery` to use database metadata:

```python
class BufferQuery:
    def __init__(self, storage_manager, db_connection):
        self.storage_manager = storage_manager
        self.db_connection = db_connection
        
    async def query_buffer(self, contract_id: int, tick_types: List[str], 
                          buffer_duration: str = "1h") -> List[Dict]:
        """Query buffer using database metadata for server selection."""
        
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - self._parse_duration(buffer_duration)
        
        # Find servers that collected data in this time range
        servers = await self._find_servers_for_timerange(contract_id, start_time, end_time)
        
        all_messages = []
        
        for server in servers:
            # Query messages from this server's storage
            messages = await self._query_server_storage(
                server, contract_id, tick_types, start_time, end_time
            )
            all_messages.extend(messages)
            
        # Sort by timestamp and return
        all_messages.sort(key=lambda m: m.get('timestamp', ''))
        return all_messages
        
    async def _find_servers_for_timerange(self, contract_id: int, 
                                        start_time: datetime, 
                                        end_time: datetime) -> List[Dict]:
        """Find servers that collected data in the given time range."""
        return await self.db_connection.fetch("""
            SELECT 
                si.storage_path,
                si.instance_name,
                cs.session_start,
                cs.session_end,
                sc.tick_types
            FROM collection_sessions cs
            JOIN server_instances si ON cs.server_instance_id = si.id
            JOIN session_contracts sc ON cs.id = sc.collection_session_id
            WHERE sc.contract_id = $1
              AND cs.session_start <= $3
              AND (cs.session_end IS NULL OR cs.session_end >= $2)
              AND cs.status IN ('active', 'completed')
            ORDER BY cs.session_start
        """, [contract_id, start_time, end_time])
```

### 3. Migration Workflow Integration

Track migration events during server handoffs:

```python
async def execute_migration(source_server: str, target_server: str, contracts: List[int]):
    """Execute migration with database tracking."""
    
    # Start migration event
    migration_id = await db.fetchval("""
        INSERT INTO migration_events 
        (event_type, event_status, source_server_id, target_server_id, 
         event_start, migration_type, contracts_migrated)
        VALUES ('handoff', 'started', 
                (SELECT id FROM server_instances WHERE instance_name = $1),
                (SELECT id FROM server_instances WHERE instance_name = $2),
                NOW(), 'blue_green', $3)
        RETURNING id
    """, [source_server, target_server, contracts])
    
    try:
        # 1. Start target server
        await start_target_server(target_server)
        
        # 2. Validate target server is collecting data
        await validate_target_collection(target_server, contracts)
        
        # 3. Stop source server gracefully
        await stop_source_server(source_server)
        
        # 4. Validate data continuity
        validation_results = await validate_data_continuity(contracts)
        
        # Mark migration as completed
        await db.execute("""
            UPDATE migration_events 
            SET event_status = 'completed', 
                event_end = NOW(),
                validation_results = $2
            WHERE id = $1
        """, [migration_id, json.dumps(validation_results)])
        
    except Exception as e:
        # Mark migration as failed
        await db.execute("""
            UPDATE migration_events 
            SET event_status = 'failed', 
                event_end = NOW(),
                notes = $2
            WHERE id = $1
        """, [migration_id, str(e)])
        raise
```

## Implementation Steps

### Phase 1: Database Setup
1. Create PostgreSQL database and tables
2. Add database connection configuration
3. Create database migration scripts
4. Add basic CRUD operations

### Phase 2: Session Tracking
1. Integrate session registration in BackgroundStreamManager
2. Track session start/stop events
3. Register tracked contracts per session
4. Add session health monitoring

### Phase 3: Query Integration
1. Update BufferQuery to use database metadata
2. Implement multi-server query logic
3. Add server selection algorithms
4. Test timeline reconstruction

### Phase 4: Migration Tracking
1. Add migration event tracking
2. Implement validation workflows
3. Add rollback capabilities
4. Create migration management CLI

### Phase 5: Monitoring & Operations
1. Add monitoring dashboards
2. Create operational runbooks
3. Add alerting for gaps/failures
4. Performance optimization

## Benefits

### 1. **Eliminates Storage Merging**
- No need to physically merge storage directories
- Keep storage paths separate and isolated
- Reduces migration complexity and risk

### 2. **Complete Audit Trail**
- Track exactly when each server was collecting data
- Identify gaps in data collection
- Validate migration success

### 3. **Flexible Reconstruction**
- Query data across multiple servers seamlessly
- Reconstruct timelines for any time range
- Handle complex migration scenarios

### 4. **Safe Migrations**
- Validate data continuity before completing migration
- Rollback capability with full audit trail
- Automated validation checks

### 5. **Operational Visibility**
- Monitor collection health across all servers
- Identify performance issues
- Track storage usage by server/contract

## Configuration

### Database Configuration
```python
# config/database.py
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'ib_stream_metadata',
    'user': 'ib_stream',
    'password': 'secure_password',
    'min_connections': 5,
    'max_connections': 20
}
```

### Server Instance Configuration
```python
# Each server instance needs unique identification
INSTANCE_CONFIG = {
    'instance_name': 'production-v1.2.3',  # Unique identifier
    'server_version': 'v1.2.3',            # Version tag
    'environment': 'production',            # Environment type
    'storage_path': '/data/ib-stream/storage',
    'tws_client_id': 2
}
```

This design provides a robust foundation for managing distributed IB Stream deployments without the complexity of storage directory merging, while maintaining complete data lineage and migration safety.