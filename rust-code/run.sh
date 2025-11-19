#!/bin/bash
# Load environment variables and run the Rust backend

set -a  # automatically export all variables
source .env
set +a

echo "🚀 Starting Rust backend with loaded environment..."
echo "   DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:0:8}..."
echo "   QU_SECRET: ${QU_SECRET:0:8}..."
echo "   PORT: $PORT"
echo ""

cargo run --release

