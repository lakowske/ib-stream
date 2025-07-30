# Docker Compose Setup for IB-Stream Project

Create a Docker Compose configuration and Dockerfile for the ib-stream project that enables containerized deployment. The project is a Python-based market data streaming service that connects to Interactive Brokers Gateway.

## Requirements

### Base Image
- Use `debian:bookworm-slim` as the base image for lightweight deployment
- Install essential system dependencies for Python development

### Dependencies to Install
- **Python 3.11+**: Runtime environment
- **pip**: Python package manager  
- **uv**: Fast Python package installer (install via pip)
- **uvicorn**: ASGI server for FastAPI applications
- **build-essential**: Compilation tools for native extensions
- **git**: For cloning dependencies if needed
- **Node.js and npm**: For Claude Code installation
- **Claude Code**: Install globally with `npm install -g @anthropic-ai/claude-code`

### Project Structure Context
The project has this structure:
- `ib-stream/`: Main streaming service with FastAPI server
- `ib-contract/`: Contract lookup service  
- `ib-util/`: Shared utilities for IB Gateway connections
- `contrib/twsapi_macunix.1030.01/`: Interactive Brokers TWS API
- `Makefile`: Build automation with targets like `setup`, `build-api`, `install-packages`

### Dockerfile Requirements

1. **Copy project files**: Copy all project directories into the container
2. **Build TWS API**: The project requires building the IB TWS API from `contrib/twsapi_macunix.1030.01/IBJts/source/pythonclient/`
3. **Use Makefile**: Use `make setup` to build the entire project, which:
   - Creates virtual environment in `.venv/`
   - Builds and installs TWS API
   - Installs ib-util, ib-stream, and ib-studies packages in development mode
4. **Expose ports**: 
   - Port 8000 for the main streaming service
   - Port 8001 for the contracts service
5. **Working directory**: Set to `/app`
6. **User setup**: Create non-root user `app` for security

### Docker Compose Requirements

Create a `docker-compose.yml` with:

1. **Single service**: `ib-stream`
   - Build from local Dockerfile  
   - Run both streaming and contract services in the same container
   - Expose both service ports
   - Mount configuration directory for environment files
   - Set environment variables for development mode

2. **Environment configuration**:
   - Support for different environments (development, staging, production)
   - Configuration mounted from `./ib-stream/config/` 
   - Environment variable `IB_STREAM_ENV` to select config file

3. **Volumes**:
   - Configuration: `./ib-stream/config:/app/ib-stream/config`
   - Storage for market data: `./storage:/app/storage`
   - Logs: `./logs:/app/logs`
   - Home directory: `./home:/home` (mount project's ./home directory to container /home)

4. **Networking**:
   - Expose ports to host for external access

### Additional Considerations

- **Single container approach**: Both streaming and contract services run in the same container
- **Process management**: Use supervisor or similar to manage both services within the container
- **Health checks**: Add health check endpoints for the main service
- **Restart policy**: Set to `unless-stopped` for production resilience  
- **Resource limits**: Include memory and CPU limits
- **Logging**: Configure Docker logging driver
- **Development override**: Provide `docker-compose.override.yml` for development with volume mounts for hot reloading

### Expected Output

Generate:
1. `Dockerfile` - Multi-stage build optimized for production with Claude Code installed
2. `docker-compose.yml` - Production-ready compose file with single service
3. `docker-compose.override.yml` - Development overrides
4. `.dockerignore` - Exclude unnecessary files from build context

The container should be ready to:
- Connect to an external IB Gateway instance and stream market data with persistent storage
- Run both streaming and contract services within a single container
- Provide access to Claude Code CLI tool
- Mount the project's ./home directory (not host /home) for limited access