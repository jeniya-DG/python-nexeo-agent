# Qu/Rust Backend Restart Script

## Quick Start

```bash
cd ~/Desktop/CODE/JITB/dg-compat-lab/rust-code
./restart_qu.sh
```

## What It Does

The `restart_qu.sh` script performs a complete restart and re-indexing of the Qu/Rust backend:

1. **Stops** the Rust backend (`nexeo-sts`)
2. **Stops and removes** the Qdrant container
3. **Clears** Qdrant storage (forces fresh re-indexing)
4. **Starts** a fresh Qdrant container
5. **Starts** the Rust backend (which will re-index the menu)
6. **Waits** for initialization to complete (~60 seconds)
7. **Verifies** that menu data is loaded
8. **Tests** that the API is responding

## When to Use

Run this script when:

- ✅ Menu data seems outdated or incorrect
- ✅ Modifiers are returning empty results
- ✅ You changed the `LOCATION_ID` in `.env`
- ✅ The Qu API data has been updated
- ✅ The Rust backend is behaving unexpectedly
- ✅ You want to force a clean re-index

## Expected Output

```
🔄 Restarting Qu/Rust Backend Service...
==========================================

1️⃣  Stopping Rust backend...
   ✅ Rust backend stopped

2️⃣  Stopping Qdrant container...
   ✅ Qdrant stopped and removed

3️⃣  Clearing Qdrant storage...
   ✅ Qdrant storage cleared

4️⃣  Starting Qdrant container...
   ✅ Qdrant started

5️⃣  Starting Rust backend...
   ✅ Rust backend started (PID: 12345)
   📋 Logs: tail -f /tmp/nexeo-sts.log

6️⃣  Waiting for services to initialize...
   ⏳ Downloading embeddings model and indexing menu (this takes ~60 seconds)...
   ✅ Rust backend API is listening on port 4000

7️⃣  Verifying menu data...
   ✅ Menu items: 339
   ✅ Modifiers: 53925

8️⃣  Testing API endpoint...
   ✅ API is responding: http://localhost:4000/menu

==========================================
✅ Qu/Rust Backend Restart Complete!
```

## Monitoring

### View Live Logs
```bash
tail -f /tmp/nexeo-sts.log
```

### Check If Running
```bash
ps aux | grep nexeo-sts
```

### Test API Manually
```bash
# Get menu
curl http://localhost:4000/menu | jq

# Query modifiers for a combo
curl -X POST http://localhost:4000/query/modifiers \
  -H "Content-Type: application/json" \
  -d '{"query": "fries", "parent": "47587-56634-105606", "limit": 5}' | jq
```

### Check Qdrant Collections
```bash
# List collections
curl -s http://localhost:6333/collections | jq

# Check menu count
curl -s http://localhost:6333/collections/menu | jq '.result.points_count'

# Check modifiers count
curl -s http://localhost:6333/collections/modifiers | jq '.result.points_count'
```

## Troubleshooting

### Script Hangs or Times Out
- Check logs: `tail -f /tmp/nexeo-sts.log`
- Common issue: LibTorch not installed (Mac M1/M2/M3)
- Solution: Make sure you're using the containerized version or have LibTorch installed

### Port Already in Use
```bash
# Find what's using port 4000
lsof -i :4000

# Kill the process
kill <PID>

# Then re-run the script
./restart_qu.sh
```

### Qdrant Won't Start
```bash
# Check if port 6333 is in use
lsof -i :6333

# Check Podman status
podman ps -a

# View Qdrant logs
podman logs qdrant
```

### Low Menu/Modifier Counts
- **Menu items < 100**: Qu API may be down or location ID is wrong
- **Modifiers < 10000**: Re-indexing incomplete, wait longer
- Check `.env` file has correct `LOCATION_ID=4776`

## Manual Stop

If you need to stop the services manually:

```bash
# Stop Rust backend
pkill -f nexeo-sts

# Stop Qdrant
podman stop qdrant && podman rm qdrant
```

## Notes

- The script automatically redirects logs to `/tmp/nexeo-sts.log`
- Initialization typically takes 60-90 seconds
- The script will wait up to 90 seconds for the API to start
- Menu data is fetched from Qu API based on `LOCATION_ID` in `.env`

