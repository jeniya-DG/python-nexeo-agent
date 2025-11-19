#!/bin/bash
# Nightly Qu Backend Refresh Script for EC2
# Runs at 4:00 AM to refresh menu data from Qu API

set -e # Exit on error

LOG_FILE="/home/ubuntu/dg-compat-lab/qu_refresh.log"
QDRANT_STORAGE="/home/ubuntu/dg-compat-lab/qdrant_storage"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting Nightly Qu Backend Refresh ==="

# 1. Stop Rust backend container
log "Stopping Rust backend (nexeo-sts)..."
podman stop nexeo-sts || log "Warning: nexeo-sts was not running"
podman rm nexeo-sts || log "Warning: Failed to remove nexeo-sts"
log "✓ Rust backend stopped"

# 2. Stop Qdrant container
log "Stopping Qdrant..."
podman stop qdrant || log "Warning: qdrant was not running"
podman rm qdrant || log "Warning: Failed to remove qdrant"
log "✓ Qdrant stopped"

# 3. Clear Qdrant storage (forces fresh re-index)
log "Clearing Qdrant storage..."
rm -rf "${QDRANT_STORAGE}"/*
log "✓ Qdrant storage cleared"

# 4. Start Qdrant container
log "Starting Qdrant..."
podman run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v "${QDRANT_STORAGE}":/qdrant/storage \
  qdrant/qdrant:latest

sleep 5
log "✓ Qdrant started"

# 5. Start Rust backend container
log "Starting Rust backend (nexeo-sts)..."
cd /home/ubuntu/dg-compat-lab/rust-code

podman run -d \
  --name nexeo-sts \
  --env-file /home/ubuntu/dg-compat-lab/.env \
  -v /home/ubuntu/dg-compat-lab/menu:/app/menu:ro \
  -v /home/ubuntu/dg-compat-lab/orders:/app/orders \
  --network host \
  localhost/nexeo-sts:latest

log "✓ Rust backend started"

# 6. Wait for services to initialize
log "Waiting 30 seconds for services to initialize..."
sleep 30

# 7. Wait for indexing to complete (check every 10 seconds, max 5 minutes)
log "Waiting for Qdrant indexing to complete..."
MAX_WAIT=300  # 5 minutes
ELAPSED=0
MENU_COUNT=0
MODIFIER_COUNT=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    MENU_COUNT=$(curl -s http://localhost:6333/collections/menu 2>/dev/null | jq -r ".result.points_count // 0" || echo "0")
    MODIFIER_COUNT=$(curl -s http://localhost:6333/collections/modifiers 2>/dev/null | jq -r ".result.points_count // 0" || echo "0")
    
    if [ "$MENU_COUNT" -gt 0 ] && [ "$MODIFIER_COUNT" -gt 0 ]; then
        log "✓ Indexing complete: Menu items: $MENU_COUNT, Modifiers: $MODIFIER_COUNT"
        break
    fi
    
    log "Still indexing... (Menu: $MENU_COUNT, Modifiers: $MODIFIER_COUNT)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ "$MENU_COUNT" -eq 0 ] || [ "$MODIFIER_COUNT" -eq 0 ]; then
    log "❌ WARNING: Indexing may have failed or is incomplete"
    log "   Menu items: $MENU_COUNT"
    log "   Modifiers: $MODIFIER_COUNT"
    log "   Check logs: podman logs nexeo-sts"
    exit 1
fi

# 8. Verify Rust backend is responding
log "Verifying Rust backend API..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4000/menu 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    log "✓ Rust backend API is responding"
else
    log "❌ WARNING: Rust backend returned HTTP $HTTP_CODE"
    exit 1
fi

# 9. Refresh Qu prices from API
log "Refreshing Qu prices from API..."
cd /home/ubuntu/dg-compat-lab || exit 1

# Activate Python virtual environment
source myenv/bin/activate || {
    log "❌ ERROR: Failed to activate Python virtual environment"
    exit 1
}

# Run price refresh script
python3 get_full_menu_with_prices.py >> "$LOG_FILE" 2>&1
PRICE_REFRESH_STATUS=$?

if [ $PRICE_REFRESH_STATUS -eq 0 ]; then
    # Count prices in the new file
    if [ -f "qu_prices_complete.json" ]; then
        PRICE_COUNT=$(grep -o '"price_count":' qu_prices_complete.json | wc -l)
        log "✓ Prices refreshed successfully ($PRICE_COUNT items)"
    else
        log "⚠️  WARNING: qu_prices_complete.json not created"
    fi
else
    log "❌ WARNING: Price refresh failed with exit code $PRICE_REFRESH_STATUS"
    log "   (Continuing with existing prices)"
fi

deactivate

log "=== Nightly Qu Backend Refresh Complete ==="
log "Menu items indexed: $MENU_COUNT"
log "Modifiers indexed: $MODIFIER_COUNT"
log ""

exit 0


