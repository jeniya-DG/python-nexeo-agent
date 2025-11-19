#!/bin/bash
# Setup script to deploy nightly Qu refresh to EC2

set -e

SSH_KEY="$HOME/.ssh/nexeo.pem"
EC2_HOST="ubuntu@3.134.46.103"

echo "🚀 Deploying Nightly Qu Refresh to EC2..."
echo ""

# 1. Copy the refresh script to EC2
echo "1. Copying refresh script to EC2..."
scp -i "$SSH_KEY" refresh_qu_nightly.sh "${EC2_HOST}:~/dg-compat-lab/"
echo "✓ Script copied"
echo ""

# 2. Make script executable and set up cron job
echo "2. Setting up cron job on EC2..."
ssh -i "$SSH_KEY" "$EC2_HOST" << 'REMOTE_SCRIPT'
cd ~/dg-compat-lab

# Make script executable
chmod +x refresh_qu_nightly.sh

# Create cron job (runs at 4:00 AM daily)
# Remove any existing cron job for this script first
(crontab -l 2>/dev/null | grep -v "refresh_qu_nightly.sh" || true) | crontab -

# Add new cron job
(crontab -l 2>/dev/null; echo "0 4 * * * /home/ubuntu/dg-compat-lab/refresh_qu_nightly.sh >> /home/ubuntu/dg-compat-lab/qu_refresh.log 2>&1") | crontab -

echo "✓ Cron job installed"
echo ""
echo "Current crontab:"
crontab -l

REMOTE_SCRIPT

echo ""
echo "✅ Nightly refresh setup complete!"
echo ""
echo "📋 Details:"
echo "   • Script: ~/dg-compat-lab/refresh_qu_nightly.sh"
echo "   • Schedule: Daily at 4:00 AM (server time)"
echo "   • Logs: ~/dg-compat-lab/qu_refresh.log"
echo ""
echo "🧪 To test the script manually:"
echo "   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 \"~/dg-compat-lab/refresh_qu_nightly.sh\""
echo ""
echo "📝 To view logs:"
echo "   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 \"tail -f ~/dg-compat-lab/qu_refresh.log\""
echo ""
echo "⏰ To verify cron job:"
echo "   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 \"crontab -l\""
echo ""


