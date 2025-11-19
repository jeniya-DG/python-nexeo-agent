#!/bin/bash
# Restart all services on EC2: Qdrant, Rust backend (nexeo-sts), and Python web service

set -e

echo "🔄 Restarting All Services on EC2..."
echo "================================================"

# EC2 connection details
EC2_USER="ubuntu"
EC2_HOST="3.134.46.103"
KEY_PATH="$HOME/.ssh/nexeo.pem"

# Connect to EC2 and restart all services
ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << 'EOF'
    echo ""
    echo "🛑 Step 1: Stopping all services..."
    echo "-----------------------------------"
    
    # Stop Python web service
    echo "   • Stopping Python web service..."
    sudo systemctl stop jitb-web || true
    
    # Stop Rust backend container
    echo "   • Stopping Rust backend (nexeo-sts)..."
    podman stop nexeo-sts || true
    podman rm nexeo-sts || true
    
    # Stop Qdrant container
    echo "   • Stopping Qdrant..."
    podman stop qdrant || true
    podman rm qdrant || true
    
    echo "✅ All services stopped"
    echo ""
    
    echo "🚀 Step 2: Starting Qdrant..."
    echo "-----------------------------------"
    podman run -d \
      --name qdrant \
      -p 6333:6333 \
      -p 6334:6334 \
      -v ~/qdrant_storage:/qdrant/storage \
      qdrant/qdrant:latest
    
    echo "   • Qdrant started, waiting for it to be ready..."
    sleep 5
    
    echo "✅ Qdrant is running"
    echo ""
    
    echo "🚀 Step 3: Starting Rust backend (nexeo-sts)..."
    echo "-----------------------------------"
    cd /home/ubuntu/dg-compat-lab/rust-code
    
    podman run -d \
      --name nexeo-sts \
      --network host \
      --env-file /home/ubuntu/dg-compat-lab/.env \
      -v ~/menu:/root/menu:ro \
      -v ~/orders:/root/orders \
      -v ~/qdrant_storage:/root/qdrant_storage:ro \
      localhost/nexeo-sts:latest
    
    echo "   • Rust backend started, waiting for initialization..."
    echo "   • (This may take 30-60 seconds for menu indexing...)"
    
    # Wait for Rust backend to be ready (port 4000)
    timeout=90
    elapsed=0
    while ! nc -z localhost 4000 && [ $elapsed -lt $timeout ]; do
      echo "   • Still loading... ($elapsed/$timeout seconds)"
      sleep 5
      elapsed=$((elapsed + 5))
    done
    
    if nc -z localhost 4000; then
      echo "✅ Rust backend is listening on port 4000"
    else
      echo "❌ Rust backend did not start within $timeout seconds"
      echo "   Check logs: podman logs nexeo-sts"
      exit 1
    fi
    
    echo ""
    
    echo "🚀 Step 4: Starting Python web service..."
    echo "-----------------------------------"
    sudo systemctl start jitb-web
    sleep 3
    
    echo "✅ Python web service started"
    echo ""
    
    echo "📊 Step 5: Verifying all services..."
    echo "-----------------------------------"
    
    # Check Qdrant
    echo "   • Qdrant status:"
    QDRANT_STATUS=$(podman ps --filter "name=qdrant" --format "{{.Status}}")
    echo "     $QDRANT_STATUS"
    
    # Check Rust backend
    echo "   • Rust backend status:"
    RUST_STATUS=$(podman ps --filter "name=nexeo-sts" --format "{{.Status}}")
    echo "     $RUST_STATUS"
    
    # Check Python service
    echo "   • Python web service status:"
    sudo systemctl is-active jitb-web
    
    # Check menu/modifier counts
    echo ""
    echo "   • Qdrant collections:"
    MENU_COUNT=$(curl -s http://localhost:6333/collections/menu 2>/dev/null | jq -r ".result.points_count" || echo "N/A")
    MODIFIER_COUNT=$(curl -s http://localhost:6333/collections/modifiers 2>/dev/null | jq -r ".result.points_count" || echo "N/A")
    echo "     - Menu items: $MENU_COUNT"
    echo "     - Modifiers: $MODIFIER_COUNT"
    
    echo ""
    echo "🎉 All services restarted successfully!"
    echo ""
    echo "📍 Service URLs:"
    echo "   • Production:     https://jitb.deepgram.com/"
    echo "   • Test:           https://jitb.deepgram.com/test"
    echo "   • Dev:            https://jitb.deepgram.com/dev"
    echo "   • Rust API:       https://jitb.deepgram.com/nexeo/menu"
    echo "   • Qdrant:         http://localhost:6333"
    echo ""
    echo "📋 View logs:"
    echo "   • Python:  sudo journalctl -u jitb-web -f"
    echo "   • Rust:    podman logs -f nexeo-sts"
    echo "   • Qdrant:  podman logs -f qdrant"
    
EOF

echo ""
echo "================================================"
echo "✅ All services on EC2 have been restarted!"
echo "================================================"

