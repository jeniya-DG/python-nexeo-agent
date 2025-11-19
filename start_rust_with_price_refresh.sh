#!/bin/bash
# Start Rust backend and refresh prices whenever menu is loaded from Qu

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Rust Backend + Price Refresh"
echo "=========================================="
echo ""

# 1. Start Rust backend (loads menu from Qu API)
echo "📦 Starting Rust backend..."
cd rust-code

# Load environment
set -a
source ../.env
set +a

# Start Rust backend in background
cargo run --release &
RUST_PID=$!
echo "   Rust backend PID: $RUST_PID"

cd ..

# 2. Wait for Rust backend to be ready (menu loaded + indexed)
echo ""
echo "⏳ Waiting for Rust backend to load menu from Qu API..."
MAX_WAIT=120  # 2 minutes max
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    # Check if Rust backend is responding
    if curl -s http://localhost:4000/menu > /dev/null 2>&1; then
        echo "   ✅ Rust backend is ready!"
        break
    fi
    
    # Check if Rust process died
    if ! ps -p $RUST_PID > /dev/null 2>&1; then
        echo "   ❌ ERROR: Rust backend process died"
        exit 1
    fi
    
    sleep 2
    WAITED=$((WAITED + 2))
    
    if [ $((WAITED % 10)) -eq 0 ]; then
        echo "   ... still waiting ($WAITED seconds)"
    fi
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "   ❌ ERROR: Rust backend did not start within $MAX_WAIT seconds"
    kill $RUST_PID 2>/dev/null || true
    exit 1
fi

# 3. Rust backend is ready - now refresh prices from Qu API
echo ""
echo "💰 Refreshing prices from Qu API..."
echo "   (Menu was just loaded, now fetching prices from same source)"
echo ""

# Activate Python virtualenv if it exists
if [ -d "myenv" ]; then
    source myenv/bin/activate
elif [ -d "../myenv" ]; then
    source ../myenv/bin/activate
fi

# Run price fetch script
python3 get_full_menu_with_prices.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Price refresh complete!"
    
    # Show price count
    if [ -f "qu_prices_complete.json" ]; then
        PRICE_COUNT=$(grep -o '"price_count": [0-9]*' qu_prices_complete.json | grep -o '[0-9]*')
        EXTRACTED_AT=$(grep -o '"extracted_at": "[^"]*"' qu_prices_complete.json | cut -d'"' -f4)
        echo "   📊 Prices: $PRICE_COUNT items"
        echo "   🕐 Updated: $EXTRACTED_AT"
    fi
else
    echo ""
    echo "⚠️  WARNING: Price refresh failed"
    echo "   Continuing with existing prices"
fi

echo ""
echo "=========================================="
echo "✅ Startup Complete"
echo "=========================================="
echo ""
echo "Rust backend is running (PID: $RUST_PID)"
echo "Prices are current with the menu just loaded from Qu"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Wait for Rust backend to finish (keep script running)
wait $RUST_PID

