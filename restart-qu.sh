#!/bin/bash
# Refresh Qu Menu - Restarts Qdrant, Rust backend, and Python service
# Run this script to fetch fresh menu data from Qu API

set -e  # Exit on error

echo "🔄 Starting Qu Menu Refresh..."
echo ""

# Step 1: Restart Qdrant (clears old data)
echo "📊 Step 1: Restarting Qdrant..."
podman stop qdrant 2>/dev/null || true
podman rm qdrant 2>/dev/null || true
rm -rf ~/dg-compat-lab/qdrant_storage/*
podman run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v ~/dg-compat-lab/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
echo "✅ Qdrant restarted"
echo ""

# Step 2: Restart Rust backend (fetches fresh menu from Qu)
echo "🦀 Step 2: Restarting Rust backend (nexeo-sts)..."
podman stop nexeo-sts 2>/dev/null || true
podman rm nexeo-sts 2>/dev/null || true
podman run -d \
  --name nexeo-sts \
  --network host \
  -v ~/dg-compat-lab/menu:/root/menu \
  -v ~/dg-compat-lab/orders:/root/orders \
  --env-file ~/dg-compat-lab/.env \
  localhost/nexeo-sts:latest
echo "✅ Rust backend restarted"
echo ""

# Step 3: Wait for indexing to complete
echo "⏳ Step 3: Waiting for menu indexing (60 seconds)..."
sleep 60
echo "✅ Wait complete"
echo ""

# Step 4: Verify menu loaded
echo "🔍 Step 4: Verifying menu data..."
MENU_COUNT=$(curl -s http://localhost:6333/collections/menu | jq -r '.result.points_count // 0')
MODIFIER_COUNT=$(curl -s http://localhost:6333/collections/modifiers | jq -r '.result.points_count // 0')
echo "   Menu items: $MENU_COUNT"
echo "   Modifiers: $MODIFIER_COUNT"

if [ "$MENU_COUNT" -gt 0 ] && [ "$MODIFIER_COUNT" -gt 0 ]; then
    echo "✅ Menu data loaded successfully"
else
    echo "⚠️  Warning: Menu data may not be loaded correctly"
    echo "   Check logs: podman logs nexeo-sts"
fi
echo ""

# Step 5: Restart Python service
echo "🐍 Step 5: Restarting Python service..."
sudo systemctl restart jitb-web
sleep 3
echo "✅ Python service restarted"
echo ""

# Step 6: Check service status
echo "📊 Step 6: Service status..."
echo "Qdrant: $(podman ps --filter name=qdrant --format '{{.Status}}')"
echo "Rust:   $(podman ps --filter name=nexeo-sts --format '{{.Status}}')"
echo "Python: $(sudo systemctl is-active jitb-web)"
echo ""

echo "🎉 Qu Menu Refresh Complete!"
echo ""
echo "📋 Next steps:"
echo "   - Check Rust logs: podman logs nexeo-sts | tail -50"
echo "   - Check Python logs: sudo journalctl -u jitb-web -n 50"
echo "   - Test the menu: https://jitb.deepgram.com/"
