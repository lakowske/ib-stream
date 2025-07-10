#!/bin/bash
# Test script for verifying reconnection logic

echo "Reconnection Test Script"
echo "======================="
echo ""
echo "This script helps test the reconnection logic by monitoring the background streaming status."
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check background status
check_status() {
    local status=$(curl -s http://localhost:8001/background/status 2>/dev/null)
    if [ $? -eq 0 ]; then
        local connected=$(echo "$status" | jq -r '.status.tws_connected')
        local streams=$(echo "$status" | jq -r '.status.total_streams')
        
        if [ "$connected" = "true" ] && [ "$streams" -gt 0 ]; then
            echo -e "${GREEN}✓ Connected${NC} - TWS connected with $streams active streams"
        elif [ "$connected" = "true" ]; then
            echo -e "${YELLOW}⚠ Connected${NC} - TWS connected but no active streams"
        else
            echo -e "${RED}✗ Disconnected${NC} - TWS not connected"
        fi
    else
        echo -e "${RED}✗ Server Down${NC} - Cannot reach server"
    fi
}

# Function to check if new files are being created
check_recording() {
    local new_files=$(find storage -type f -newermt "30 seconds ago" 2>/dev/null | wc -l)
    if [ "$new_files" -gt 0 ]; then
        echo -e "${GREEN}✓ Recording${NC} - $new_files new files in last 30 seconds"
    else
        echo -e "${RED}✗ Not Recording${NC} - No new files in last 30 seconds"
    fi
}

echo "Starting monitoring... (Press Ctrl+C to stop)"
echo ""
echo "To test reconnection:"
echo "1. Stop TWS/Gateway"
echo "2. Wait for disconnection detection (within 10 seconds)"
echo "3. Restart TWS/Gateway"
echo "4. Watch for automatic reconnection (within 3 seconds of TWS startup)"
echo ""

# Main monitoring loop
while true; do
    echo -n "$(date '+%H:%M:%S') - "
    check_status
    echo -n "          - "
    check_recording
    
    # Also check for recent disconnection/reconnection events in logs
    recent_disconnect=$(tail -100 /home/seth/Software/dev/ib-stream/ib-stream/logs/ib-stream-tracked_error.log 2>/dev/null | grep -c "TWS disconnection detected")
    recent_reconnect=$(tail -100 /home/seth/Software/dev/ib-stream/ib-stream/logs/ib-stream-tracked_error.log 2>/dev/null | grep -c "TWS reconnected, restarting")
    
    if [ "$recent_disconnect" -gt 0 ] || [ "$recent_reconnect" -gt 0 ]; then
        echo -e "          ${YELLOW}→ Recent events: Disconnections=$recent_disconnect, Reconnections=$recent_reconnect${NC}"
    fi
    
    sleep 5
done