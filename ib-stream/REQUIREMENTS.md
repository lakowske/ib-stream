# System Requirements

This document outlines all system-level dependencies required to build and run ib-stream with storage capabilities.

## Operating System Support

- **Linux**: Ubuntu 20.04+, Debian 11+, CentOS 8+, RHEL 8+
- **macOS**: 11.0+ (Big Sur)
- **Windows**: 10+ (with WSL2 recommended for development)

## System Dependencies

### Protocol Buffers Compiler

Required for generating Python protobuf classes from `.proto` schema files.

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install -y protobuf-compiler
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y protobuf-compiler
# or for older versions:
sudo yum install -y protobuf-compiler
```

**macOS (Homebrew):**
```bash
brew install protobuf
```

**Windows:**
- Download from [Protocol Buffers releases](https://github.com/protocolbuffers/protobuf/releases)
- Add to PATH

### PostgreSQL (Optional)

Required for storage indexing and metadata tracking. Can be disabled via configuration.

**Debian/Ubuntu:**
```bash
sudo apt install -y postgresql postgresql-contrib
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y postgresql postgresql-server postgresql-contrib
```

**macOS (Homebrew):**
```bash
brew install postgresql
```

**Docker Alternative:**
```bash
docker run -d \
  --name ib-stream-postgres \
  -e POSTGRES_DB=ib_stream \
  -e POSTGRES_USER=ib_stream \
  -e POSTGRES_PASSWORD=ib_stream \
  -p 5432:5432 \
  postgres:15
```

### Python Development Headers

Required for building some Python packages with C extensions.

**Debian/Ubuntu:**
```bash
sudo apt install -y python3-dev python3-pip python3-venv
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf install -y python3-devel python3-pip python3-virtualenv
```

**macOS:**
```bash
# Usually included with Xcode Command Line Tools
xcode-select --install
```

### Build Tools

**Debian/Ubuntu:**
```bash
sudo apt install -y build-essential pkg-config
```

**RHEL/CentOS/Fedora:**
```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y pkgconfig
```

**macOS:**
```bash
xcode-select --install
```

## Python Requirements

- **Python**: 3.8+ (3.9+ recommended)
- **pip**: Latest version
- **venv**: For virtual environments

### Virtual Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

## Interactive Brokers Requirements

### TWS or IB Gateway

- **TWS (Trader Workstation)**: Latest version
- **IB Gateway**: Latest version (lightweight alternative)

### Configuration

1. Enable API connections in TWS/Gateway:
   - Go to Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set Socket port (default: 7497 for paper, 7496 for live)
   - Enable "Read-Only API" for data-only access

2. Default ports:
   - Paper TWS: 7497
   - Live TWS: 7496  
   - Paper Gateway: 4002
   - Live Gateway: 4001

## Storage Requirements

### Disk Space

Estimated storage requirements per contract per day:

- **JSON Format**: ~500MB - 2GB (depending on activity)
- **Protobuf Format**: ~200MB - 800MB (60-70% compression)
- **PostgreSQL Index**: ~50MB - 200MB

### File System

- **Linux/macOS**: Any POSIX-compliant filesystem (ext4, XFS, APFS, etc.)
- **Windows**: NTFS recommended
- **Network Storage**: NFS, SMB, or cloud storage supported

## Network Requirements

### Ports

- **TWS/Gateway**: 7496, 7497, 4001, 4002 (configurable)
- **HTTP API**: 8001 (default, configurable)
- **Contract API**: 8000 (default, configurable)
- **PostgreSQL**: 5432 (if using external database)

### Bandwidth

- **Market Data**: 1-10 Mbps per active contract (depends on activity)
- **API Usage**: Minimal (HTTP requests only)

## Development Requirements

### Additional Tools

**Code Quality:**
```bash
pip install ruff pytest pytest-cov
```

**Database Administration:**
```bash
# Optional PostgreSQL tools
sudo apt install -y postgresql-client  # Debian/Ubuntu
```

## Quick Start Installation

### Complete Setup (Debian/Ubuntu)

```bash
# System dependencies
sudo apt update
sudo apt install -y \
    protobuf-compiler \
    postgresql postgresql-contrib \
    python3-dev python3-pip python3-venv \
    build-essential pkg-config

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Install project
pip install -e .

# Generate protobuf files
cd src/ib_stream/storage
protoc --python_out=proto --proto_path=proto proto/tick_stream.proto
```

### Minimal Setup (No PostgreSQL)

```bash
# System dependencies
sudo apt update
sudo apt install -y protobuf-compiler python3-dev python3-pip python3-venv

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Install project
pip install -e .

# Generate protobuf files
cd src/ib_stream/storage
protoc --python_out=proto --proto_path=proto proto/tick_stream.proto

# Disable PostgreSQL in configuration
export IB_STREAM_ENABLE_POSTGRES=false
```

## Verification

### Test System Dependencies

```bash
# Check protobuf compiler
protoc --version

# Check PostgreSQL (if installed)
psql --version

# Check Python
python3 --version
pip --version
```

### Test Project Installation

```bash
# Activate virtual environment
source .venv/bin/activate

# Test imports
python -c "
import ib_stream
from ib_stream.storage import MultiStorage
print('✓ Installation successful')
"
```

## Troubleshooting

### Common Issues

**Protobuf compiler not found:**
```bash
# Check if installed
which protoc
# If not found, install per OS instructions above
```

**PostgreSQL connection issues:**
```bash
# Check if running
sudo systemctl status postgresql
# Start if needed
sudo systemctl start postgresql
```

**Python package build failures:**
```bash
# Install development headers
sudo apt install -y python3-dev build-essential
```

**Permission errors:**
```bash
# Check file permissions
ls -la storage/
# Create storage directory if needed
mkdir -p storage
chmod 755 storage
```

### Performance Tuning

**PostgreSQL (if using):**
```sql
-- Recommended settings for small to medium deployments
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
SELECT pg_reload_conf();
```

**File System:**
```bash
# For high-frequency trading, consider:
# - SSD storage for hot data
# - Separate mount for storage directory
# - Regular cleanup of old files
```

## Version Compatibility

| Component | Minimum | Recommended | Tested |
|-----------|---------|-------------|---------|
| Python | 3.8 | 3.11+ | 3.9, 3.10, 3.11 |
| protobuf | 3.19 | 4.0+ | 4.25 |
| PostgreSQL | 12 | 15+ | 13, 14, 15 |
| TWS/Gateway | 10.19 | Latest | 10.30 |

For the most up-to-date compatibility information, see the project's CI configuration.