#!/bin/bash

# Setup script for local development environment
# Run this before building: source ./setup-local-env.sh

export LIBTORCH=$(pwd)/libtorch
export LD_LIBRARY_PATH=${LIBTORCH}/lib:$LD_LIBRARY_PATH

# Set menu directory to local path
export MENU_DIRECTORY=$(pwd)/menu

# Create menu directory if it doesn't exist
mkdir -p $MENU_DIRECTORY

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "✅ Local development environment setup complete!"
echo "LIBTORCH: $LIBTORCH"
echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo ""
echo "You can now run:"
echo "  cargo build --release    # Build the application"
echo "  cargo run                # Build and run the application"
echo ""
