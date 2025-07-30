# Storage Optimization V3 Implementation

## Objective

You are tasked with implementing a complete storage optimization for the IB Stream project. This is a large, critical change that requires careful upfront planning before any implementation begins. Your role is to:

1. **Research and analyze** the complete codebase to understand all storage dependencies
2. **Create a detailed implementation plan** with comprehensive impact analysis
3. **Document every affected component** and migration strategy
4. **Remove all v2 protocol functionality** and replace with optimized storage
5. **Move the storage engine to ib-util** for reusability across tools

## Background

The project currently uses a v2 protocol format with nested JSON structures and `stream_id` based organization. The storage optimization specification in `docs/STORAGE_OPTIMIZATION_SPEC.md` defines a new optimized format that reduces storage by 50%+ by using:

- Shortened field names (`ts` vs `timestamp`, `cid` vs `contract_id`)
- Flat message structure (no nested `data` and `metadata` objects)
- Hash-based request IDs instead of complex stream IDs
- Conditional fields that are omitted when not applicable
- New file organization using `{contract_id}_{tick_type}_{timestamp}.jsonl`

## Critical Requirements

### 🚨 PLANNING FIRST APPROACH

**DO NOT START CODING IMMEDIATELY.** This is a complex migration that touches many systems. You MUST:

1. **Comprehensive Research Phase** (Required):
   - Read and understand ALL storage-related files
   - Map ALL dependencies on current v2 protocol format
   - Identify ALL components that use `stream_id`, `metadata`, or nested `data` structures
   - Document ALL external integrations (ib-studies, CLI tools, APIs)
   - Create dependency graph showing impact relationships

2. **Detailed Planning Phase** (Required):
   - Create step-by-step migration plan with clear phases
   - Design new storage engine architecture in ib-util
   - Define testing strategy for each phase
   - Identify risk mitigation strategies

3. **Documentation Phase** (Required):
   - Create comprehensive implementation plan document in `docs/`
   - Document every affected file and required changes
   - Document migration risks and mitigation strategies
   - Document testing requirements for each component

### Storage Engine Requirements

The new storage engine must be implemented in `ib-util/ib_util/storage/` and include:

- **Core Storage Engine**: Base classes for different storage backends
- **TickMessage Model**: Optimized dataclass with field validation
- **Storage Backends**: JSON, Protobuf, and potentially others
- **Query Interface**: Fast retrieval using new file organization
- **Migration Utilities**: Tools for data migration (if needed)

### Breaking Changes - Full v2 Removal

This implementation must **completely remove** all v2 protocol functionality:

- Remove all `stream_id` generation and usage
- Remove all `metadata` object creation and parsing
- Remove nested `data` object structures
- Update ALL APIs to use optimized format
- Update ALL client integrations
- Update ALL storage backends
- Update ALL testing infrastructure

## Scope Analysis

Based on the specification, you need to analyze and plan changes for:

### Core Storage Systems
- `ib-stream/src/ib_stream/storage/json_storage.py` - JSON Lines storage
- `ib-stream/src/ib_stream/storage/protobuf_storage.py` - Binary protobuf storage
- `ib-stream/src/ib_stream/storage/buffer_query.py` - Query interface
- `ib-stream/src/ib_stream/storage/multi_storage.py` - Multi-backend coordination
- `ib-stream/src/ib_stream/storage/proto/` - Protobuf schemas

### Stream Management
- `ib-stream/src/ib_stream/stream_manager.py` - Core stream handling
- `ib-stream/src/ib_stream/stream_id.py` - Stream ID generation (to be removed)
- `ib-stream/src/ib_stream/streaming_app.py` - IB API integration
- `ib-stream/src/ib_stream/streaming_core.py` - Core streaming logic
- `ib-stream/src/ib_stream/background_stream_manager.py` - Background services

### API Layer
- `ib-stream/src/ib_stream/endpoints/streaming.py` - HTTP streaming APIs
- `ib-stream/src/ib_stream/endpoints/websocket.py` - WebSocket APIs
- `ib-stream/src/ib_stream/ws_manager.py` - WebSocket management
- `ib-stream/src/ib_stream/ws_schemas.py` - WebSocket message schemas
- `ib-stream/src/ib_stream/protocol_types.py` - Protocol type definitions

### External Integration
- `ib-studies/` - Analysis and study tools
- `ib-contract/` - Contract lookup service
- CLI tools and utilities
- Monitoring and metrics systems

### Testing Infrastructure
- All unit tests using current message format
- Integration tests with storage validation
- Performance benchmarks
- Mock data and fixtures

## Research Tasks

Before creating your implementation plan, you must:

### 1. Storage Dependency Analysis
- Map every file that reads or writes storage messages
- Identify all code that depends on `stream_id`, `metadata`, or nested `data`
- Document all query patterns and file organization dependencies
- Analyze performance implications of file organization changes

### 2. API Impact Analysis
- Document all HTTP and WebSocket endpoints that return message data
- Map message routing logic that depends on current format
- Analyze authentication and session management impacts

### 3. External Integration Analysis
- Review ib-studies integration and data analysis patterns
- Document CLI tool dependencies on message format
- Identify monitoring and alerting systems that parse messages
- Map debugging and logging dependencies

### 4. Data Migration Analysis
- Plan fresh storage implementation (no existing data migration needed)
- Analyze storage volume and performance requirements for new format
- Document rollback strategies for development iterations

## Implementation Planning

After research, create a detailed implementation plan that includes:

### Phase Planning
1. **Foundation Phase**: ib-util storage engine and TickMessage model
2. **Storage Phase**: New storage backends and file organization
3. **Core Phase**: Stream management and processing pipeline updates
4. **API Phase**: HTTP and WebSocket endpoint updates
5. **Integration Phase**: External tool and service updates
6. **Testing Phase**: Comprehensive validation and performance testing

### Risk Mitigation
- Identify high-risk changes and mitigation strategies
- Plan for rollback scenarios
- Design validation checkpoints between phases
- Document emergency procedures

### Testing Strategy
- Unit test updates for each component
- Integration test scenarios
- Performance benchmarking approach
- End-to-end validation procedures

## Documentation Requirements

Create comprehensive documentation in `docs/` that includes:

### Implementation Plan Document
- **File**: `docs/STORAGE_V3_IMPLEMENTATION_PLAN.md`
- Complete phase-by-phase implementation strategy
- Detailed file-by-file change requirements
- Risk analysis and mitigation strategies
- Testing and validation procedures

### Component Impact Analysis
- **File**: `docs/STORAGE_V3_COMPONENT_ANALYSIS.md`
- Detailed analysis of every affected file
- Dependencies and impact relationships
- Change complexity ratings
- Migration requirements for each component

### New Storage Engine Architecture
- **File**: `docs/STORAGE_V3_ARCHITECTURE.md`
- ib-util storage engine design
- Storage backend interfaces
- Query optimization strategies
- Performance characteristics

## Success Criteria

Your implementation is successful when:

1. **Complete v2 Removal**: No traces of v2 protocol format remain
2. **Storage Optimization**: 50%+ storage reduction achieved
3. **Reusable Engine**: Storage engine in ib-util supports multiple tools
4. **Full Functionality**: All features work with optimized format
5. **Performance Improvement**: Faster queries and reduced I/O
6. **Comprehensive Testing**: All tests pass with new format
7. **External Integration**: ib-studies and other tools updated to new format

## Getting Started

1. **Start with comprehensive research** - Don't write any code yet
2. **Read the storage optimization spec thoroughly**
3. **Analyze the current codebase systematically**
4. **Create detailed documentation first**
5. **Get approval on the plan before implementing**

Remember: This is a critical infrastructure change. Thorough planning prevents major issues during implementation. Take the time to understand the full scope before beginning any code changes.

## Questions to Answer During Research

As you research, document answers to these critical questions:

### Storage Questions
- How is the current file organization used for queries?
- What are the performance characteristics of current vs new organization?
- Are there any data retention or archival processes that depend on current format?
- How do the different storage backends (JSON, protobuf) interact?

### Integration Questions  
- Which external tools directly read storage files vs use APIs?
- Are there any automated processes that depend on current message format?
- What monitoring or alerting systems parse message content?
- How will external tools be updated to use the new format?

### Implementation Questions
- Can the implementation be done incrementally or must it be atomic?
- What is the testing strategy for each implementation phase?
- How will you validate the new storage format works correctly?

### Testing Questions
- How will you ensure no functionality is lost during implementation?
- What performance benchmarks need to be maintained?
- How will you test with realistic data volumes?
- What rollback procedures are needed if issues are discovered during development?

Answer these questions thoroughly in your research phase before proceeding to implementation planning.