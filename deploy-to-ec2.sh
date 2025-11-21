#!/bin/bash
# Deploy latest code to EC2 via SCP and restart services

set -e

EC2_USER="ubuntu"
EC2_HOST="3.134.46.103"
KEY_PATH="$HOME/.ssh/nexeo.pem"
LOCAL_DIR="$PWD"
REMOTE_DIR="/home/ubuntu/dg-compat-lab"

echo "🚀 Deploying latest code to EC2 via SCP..."
echo "==========================================="

# Step 1: Push local changes to GitHub (for backup)
echo ""
echo "📤 Step 1: Pushing to GitHub (backup)..."
git add -A
git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')" || echo "No changes to commit"
git push origin main

# Step 2: Copy Python files to EC2
echo ""
echo "📦 Step 2: Copying Python files to EC2..."
scp -i "$KEY_PATH" \
    "$LOCAL_DIR/web_voice_agent_server.py" \
    "$LOCAL_DIR/jitb_functions.py" \
    "$LOCAL_DIR/agent_config.py" \
    "$LOCAL_DIR/latency_tracker.py" \
    "$EC2_USER@$EC2_HOST:$REMOTE_DIR/"

echo "   ✓ Python files copied"

# Step 3: Copy other important files
echo ""
echo "📦 Step 3: Copying other files..."
scp -i "$KEY_PATH" \
    "$LOCAL_DIR/qu_prices_complete.json" \
    "$LOCAL_DIR/requirements.txt" \
    "$EC2_USER@$EC2_HOST:$REMOTE_DIR/" 2>/dev/null || echo "   ⚠ Some files might not exist locally"

# Step 4: Restart service on EC2
echo ""
echo "🔄 Step 4: Restarting Python web service on EC2..."
ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << 'EOF'
    echo "   • Stopping Python web service..."
    sudo systemctl stop jitb-web.service
    
    echo "   • Starting Python web service..."
    sudo systemctl start jitb-web.service
    
    echo "   • Waiting for service to start..."
    sleep 3
    
    echo ""
    echo "✅ Deployment complete!"
    echo ""
    echo "📊 Service status:"
    sudo systemctl status jitb-web.service --no-pager -l | head -10
EOF

echo ""
echo "🧪 Testing endpoint..."
sleep 2
curl -s http://3.134.46.103:5002/health | python3 -m json.tool || echo "⚠️  Health check failed"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 To view logs, run:"
echo "   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 'sudo journalctl -u jitb-web.service -f'"

