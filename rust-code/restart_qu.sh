#!/bin/bash
# Restart Qu/Rust backend and re-index menu data
# This script stops everything, clears Qdrant storage, and starts fresh

set -e  # Exit on error

echo "🔄 Restarting Qu/Rust Backend Service..."
echo "=========================================="
echo ""

# Step 1: Stop Rust backend
echo "1️⃣  Stopping Rust backend..."
pkill -f "nexeo-sts" || echo "   (No nexeo-sts process found)"
sleep 2
echo "   ✅ Rust backend stopped"
echo ""

# Step 2: Stop and remove Qdrant container
echo "2️⃣  Stopping Qdrant container..."
podman stop qdrant 2>/dev/null || echo "   (Qdrant not running)"
podman rm qdrant 2>/dev/null || echo "   (Qdrant container already removed)"
echo "   ✅ Qdrant stopped and removed"
echo ""

# Step 3: Clear Qdrant storage to force re-indexing
echo "3️⃣  Clearing Qdrant storage..."
rm -rf ~/qdrant_storage
mkdir -p ~/qdrant_storage
chmod 777 ~/qdrant_storage
echo "   ✅ Qdrant storage cleared"
echo ""

# Step 4: Start fresh Qdrant container
echo "4️⃣  Starting Qdrant container..."
podman run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v ~/qdrant_storage:/qdrant/storage:z \
  docker.io/qdrant/qdrant:latest
echo "   ✅ Qdrant started"
echo ""

# Step 5: Start Rust backend
echo "5️⃣  Starting Rust backend..."
cd "$(dirname "$0")"  # Navigate to rust-code directory

# Kill any existing background run.sh processes
pkill -f "./run.sh" 2>/dev/null || true

# Start in background and redirect output
nohup ./run.sh > /tmp/nexeo-sts.log 2>&1 &
RUST_PID=$!
echo "   ✅ Rust backend started (PID: $RUST_PID)"
echo "   📋 Logs: tail -f /tmp/nexeo-sts.log"
echo ""

# Step 6: Wait for initialization
echo "6️⃣  Waiting for services to initialize..."
echo "   ⏳ Downloading embeddings model and indexing menu (this takes ~60 seconds)..."

# Wait for port 4000 to be available (max 90 seconds)
COUNTER=0
MAX_WAIT=90
while [ $COUNTER -lt $MAX_WAIT ]; do
    if lsof -i :4000 2>/dev/null | grep -q LISTEN; then
        echo "   ✅ Rust backend API is listening on port 4000"
        break
    fi
    sleep 2
    COUNTER=$((COUNTER + 2))
    if [ $((COUNTER % 10)) -eq 0 ]; then
        echo "   ⏳ Still initializing... ($COUNTER/$MAX_WAIT seconds)"
    fi
done

if [ $COUNTER -ge $MAX_WAIT ]; then
    echo "   ❌ Timeout waiting for Rust backend to start"
    echo "   Check logs: tail -f /tmp/nexeo-sts.log"
    exit 1
fi

echo ""

# Step 7: Verify indexing
echo "7️⃣  Verifying menu data..."
sleep 3  # Give it a moment to finish indexing

MENU_COUNT=$(curl -s http://localhost:6333/collections/menu 2>/dev/null | jq -r '.result.points_count' 2>/dev/null || echo "0")
MODIFIER_COUNT=$(curl -s http://localhost:6333/collections/modifiers 2>/dev/null | jq -r '.result.points_count' 2>/dev/null || echo "0")

if [ "$MENU_COUNT" -gt 0 ] && [ "$MODIFIER_COUNT" -gt 0 ]; then
    echo "   ✅ Menu items: $MENU_COUNT"
    echo "   ✅ Modifiers: $MODIFIER_COUNT"
else
    echo "   ⚠️  Warning: Indexing may still be in progress"
    echo "   Menu items: $MENU_COUNT"
    echo "   Modifiers: $MODIFIER_COUNT"
fi

echo ""

# Step 8: Test API
echo "8️⃣  Testing API endpoint..."
if curl -s -f http://localhost:4000/menu > /dev/null 2>&1; then
    echo "   ✅ API is responding: http://localhost:4000/menu"
else
    echo "   ⚠️  API test failed (may still be initializing)"
fi

echo ""
echo "=========================================="
echo "✅ Qu/Rust Backend Restart Complete!"
echo ""
echo "📊 Quick Stats:"
echo "   • Rust backend PID: $RUST_PID"
echo "   • API endpoint: http://localhost:4000"
echo "   • Qdrant admin: http://localhost:6333/dashboard"
echo "   • Log file: /tmp/nexeo-sts.log"
echo ""
echo "🔍 Useful commands:"
echo "   • View logs:    tail -f /tmp/nexeo-sts.log"
echo "   • Check status: ps aux | grep nexeo-sts"
echo "   • Test API:     curl http://localhost:4000/menu | jq"
echo "   • Stop service: pkill -f nexeo-sts"
echo ""

