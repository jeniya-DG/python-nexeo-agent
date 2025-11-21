# EC2 Restart Guide

Complete guide for restarting the EC2 instance and verifying all services.

## Table of Contents
- [Quick Reference](#quick-reference)
- [Full Restart Procedure](#full-restart-procedure)
- [Service-Only Restart](#service-only-restart)
- [Verification Steps](#verification-steps)
- [Troubleshooting](#troubleshooting)

---

## Quick Reference

### EC2 Connection
```bash
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103
```

### Service Restart Commands
```bash
# Restart Python web server (systemd)
sudo systemctl restart jitb-web.service

# Restart Rust backend (manual)
cd ~/dg-compat-lab/rust-code
./run.sh

# Check service status
sudo systemctl status jitb-web.service
```

---

## Full Restart Procedure

### Option 1: AWS Console Restart

1. **Log into AWS Console**
   - Navigate to EC2 Dashboard
   - Find instance: `nexeo-sts` or IP `3.134.46.103`

2. **Reboot Instance**
   - Select instance → Actions → Instance State → Reboot
   - Wait 2-3 minutes for reboot to complete

3. **Verify SSH Access**
   ```bash
   ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103
   ```

4. **Check Services Auto-Started**
   ```bash
   # Check Python web server (should auto-start via systemd)
   sudo systemctl status jitb-web.service
   
   # Check if Rust backend is running
   ps aux | grep nexeo-sts
   ```

5. **Start Services if Needed**
   ```bash
   # If Python web server not running
   sudo systemctl start jitb-web.service
   
   # If Rust backend not running
   cd ~/dg-compat-lab/rust-code
   screen -dmS rust-backend ./run.sh
   ```

### Option 2: SSH Reboot Command

```bash
# Connect and reboot
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 'sudo reboot'

# Wait 2-3 minutes, then reconnect
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103
```

---

## Service-Only Restart

**When to use:** Application changes, no system-level restart needed.

### Restart Python Web Server

```bash
# Connect to EC2
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103

# Restart the service
sudo systemctl restart jitb-web.service

# Verify it's running
sudo systemctl status jitb-web.service

# Check logs
sudo journalctl -u jitb-web.service -f
```

### Restart Rust Backend

```bash
# Connect to EC2
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103

# Stop existing process
pkill nexeo-sts

# Navigate to rust-code directory
cd ~/dg-compat-lab/rust-code

# Start in screen session
screen -dmS rust-backend ./run.sh

# Verify it started
screen -ls
ps aux | grep nexeo-sts
```

### Restart Both Services

```bash
# Quick restart script
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 << 'EOF'
echo "🔄 Restarting Python web server..."
sudo systemctl restart jitb-web.service

echo "🔄 Restarting Rust backend..."
pkill nexeo-sts
cd ~/dg-compat-lab/rust-code
screen -dmS rust-backend ./run.sh

echo ""
echo "✅ Services restarted!"
echo ""
echo "📊 Status:"
sudo systemctl status jitb-web.service --no-pager -l
ps aux | grep nexeo-sts | grep -v grep
EOF
```

---

## Verification Steps

### 1. Check Python Web Server

```bash
# Status check
sudo systemctl status jitb-web.service

# Expected output:
# ● jitb-web.service - JITB Deepgram Agent Web Server
#    Loaded: loaded
#    Active: active (running)

# Test endpoint
curl http://localhost:5002/health
# Expected: {"status": "healthy", ...}
```

### 2. Check Rust Backend

```bash
# Process check
ps aux | grep nexeo-sts

# Port check
sudo ss -tlnp | grep 8080
# Expected: LISTEN on 0.0.0.0:8080

# Test endpoint
curl http://localhost:8080/health
# Expected: {"status": "ok"}
```

### 3. Check Logs

```bash
# Python web server logs
sudo journalctl -u jitb-web.service -n 50 --no-pager

# Or check log file
tail -f ~/dg-compat-lab/jitb-web-full.log

# Rust backend logs (if in screen)
screen -r rust-backend
# Press Ctrl+A, then D to detach
```

### 4. End-to-End Test

```bash
# Test from local machine
curl https://3.134.46.103:5002/health

# Expected response:
# {
#   "status": "healthy",
#   "rust_backend": "connected",
#   "deepgram": "configured"
# }
```

---

## Troubleshooting

### Python Web Server Won't Start

```bash
# Check logs for errors
sudo journalctl -u jitb-web.service -n 100 --no-pager

# Common issues:
# 1. Port 5002 already in use
sudo lsof -i :5002
sudo kill -9 <PID>

# 2. Missing dependencies
cd ~/dg-compat-lab
source myenv/bin/activate
pip install -r requirements.txt

# 3. Missing .env file
ls -la ~/dg-compat-lab/.env
# Should exist with DEEPGRAM_API_KEY

# Restart service
sudo systemctl restart jitb-web.service
```

### Rust Backend Won't Start

```bash
# Check if binary exists
ls -la ~/dg-compat-lab/rust-code/target/release/nexeo-sts

# If missing, rebuild
cd ~/dg-compat-lab/rust-code
cargo build --release

# Check port availability
sudo lsof -i :8080
sudo kill -9 <PID>

# Check Qdrant is running
curl http://localhost:6333/health

# Start with logging
cd ~/dg-compat-lab/rust-code
RUST_LOG=debug ./run.sh
```

### Qdrant Not Running

```bash
# Check if running
docker ps | grep qdrant
# OR
podman ps | grep qdrant

# Start Qdrant
cd ~/dg-compat-lab/rust-code
docker-compose up -d
# OR
podman-compose up -d

# Verify
curl http://localhost:6333/health
```

### Port Already in Use

```bash
# Find process using port 5002 (Python)
sudo lsof -i :5002
sudo kill -9 <PID>

# Find process using port 8080 (Rust)
sudo lsof -i :8080
sudo kill -9 <PID>

# Restart services
sudo systemctl restart jitb-web.service
cd ~/dg-compat-lab/rust-code && screen -dmS rust-backend ./run.sh
```

### Screen Sessions Not Working

```bash
# List all screen sessions
screen -ls

# Kill a stuck session
screen -X -S rust-backend quit

# Create new session
screen -dmS rust-backend ./run.sh

# Attach to session (for debugging)
screen -r rust-backend
# Ctrl+A, D to detach
```

### SSL/HTTPS Issues

```bash
# Check nginx status
sudo systemctl status nginx

# Check SSL certificate
sudo certbot certificates

# Renew certificate if needed
sudo certbot renew

# Restart nginx
sudo systemctl restart nginx
```

### After EC2 Stop/Start (IP Change Warning)

⚠️ **Note:** Stopping and starting (not rebooting) EC2 changes the public IP!

```bash
# Get new IP
aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[0].Instances[0].PublicIpAddress'

# Update DNS/documentation with new IP
# Update local SSH config if needed
```

---

## Automated Restart Script

Save this as `restart_ec2_services.sh`:

```bash
#!/bin/bash

# Quick restart script for EC2 services
# Usage: ./restart_ec2_services.sh

set -e

EC2_HOST="ubuntu@3.134.46.103"
SSH_KEY="~/.ssh/nexeo.pem"

echo "🔄 Restarting services on EC2..."

ssh -i "$SSH_KEY" "$EC2_HOST" << 'EOF'
    echo "📍 Stopping services..."
    sudo systemctl stop jitb-web.service
    pkill nexeo-sts || true
    
    echo "⏳ Waiting 2 seconds..."
    sleep 2
    
    echo "🚀 Starting Python web server..."
    sudo systemctl start jitb-web.service
    
    echo "🚀 Starting Rust backend..."
    cd ~/dg-compat-lab/rust-code
    screen -dmS rust-backend ./run.sh
    
    echo "⏳ Waiting for services to start..."
    sleep 3
    
    echo ""
    echo "✅ Restart complete!"
    echo ""
    echo "📊 Service Status:"
    echo "=================="
    
    echo "Python Web Server:"
    sudo systemctl status jitb-web.service --no-pager -l | head -5
    
    echo ""
    echo "Rust Backend:"
    ps aux | grep nexeo-sts | grep -v grep || echo "⚠️  Not running"
    
    echo ""
    echo "📡 Port Status:"
    sudo ss -tlnp | grep -E ':(5002|8080|6333)' || echo "⚠️  Ports not listening"
EOF

echo ""
echo "🧪 Testing endpoints..."
sleep 2

echo "Health check:"
curl -s http://3.134.46.103:5002/health | python3 -m json.tool || echo "❌ Health check failed"

echo ""
echo "✅ Restart complete!"
```

Make it executable:
```bash
chmod +x restart_ec2_services.sh
```

---

## Monitoring After Restart

### Watch Logs Live

```bash
# Python web server
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 \
  'sudo journalctl -u jitb-web.service -f'

# Or from log file
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 \
  'tail -f ~/dg-compat-lab/jitb-web-full.log'

# Rust backend (if in screen)
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103
screen -r rust-backend
```

### Check Resource Usage

```bash
# CPU and memory
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 'top -bn1 | head -20'

# Disk space
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 'df -h'

# Network connections
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103 'sudo ss -tunap | grep -E "(5002|8080)"'
```

---

## Related Documentation

- [System Architecture](SYSTEM_ARCHITECTURE_SUMMARY.md)
- [Deployment Guide](README.md#deployment)
- [Web UI README](WEB_UI_README.md)
- [Python-Rust Bridge](python-rust-bridge.md)

---

## Quick Commands Cheat Sheet

```bash
# Connect
ssh -i ~/.ssh/nexeo.pem ubuntu@3.134.46.103

# Restart Python
sudo systemctl restart jitb-web.service

# Restart Rust
pkill nexeo-sts && cd ~/dg-compat-lab/rust-code && screen -dmS rust-backend ./run.sh

# Check status
sudo systemctl status jitb-web.service
ps aux | grep nexeo-sts

# View logs
sudo journalctl -u jitb-web.service -f
screen -r rust-backend

# Test endpoints
curl http://localhost:5002/health
curl http://localhost:8080/health
```

---

*Last updated: 2025-11-21*

