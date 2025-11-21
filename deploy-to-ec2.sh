#!/bin/bash
# Deploy latest code to EC2 and restart services

set -e

EC2_USER="ubuntu"
EC2_HOST="3.134.46.103"
KEY_PATH="$HOME/.ssh/nexeo.pem"
REPO_DIR="dg-compat-lab"

echo "🚀 Deploying latest code to EC2..."
echo "=================================="

# Step 1: Push local changes to GitHub
echo ""
echo "📤 Step 1: Pushing to GitHub..."
git add -A
git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')" || echo "No changes to commit"
git push origin main

# Step 2: Pull on EC2 and restart
echo ""
echo "📥 Step 2: Pulling on EC2 and restarting services..."
ssh -i "$KEY_PATH" "$EC2_USER@$EC2_HOST" << 'EOF'
    cd ~/dg-compat-lab
    
    echo "   • Pulling latest code from GitHub..."
    git pull origin main
    
    echo "   • Stopping Python web service..."
    sudo systemctl stop jitb-web.service
    
    echo "   • Restarting Python web service..."
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

