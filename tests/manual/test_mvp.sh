#!/bin/bash
# MVP Test Script for tx2tx
# This demonstrates the basic functionality on a single display

echo "==================================================================="
echo "tx2tx MVP Test"
echo "==================================================================="
echo ""
echo "This script will:"
echo "1. Start the tx2tx server on port 24800"
echo "2. Wait for you to move the cursor off the screen edge"
echo "3. Show that boundary detection works"
echo ""
echo "For a REAL two-display test:"
echo "- On Device 1 (Server): Run 'PYTHONPATH=src python -m tx2tx.server.main --config config.yml'"
echo "- On Device 2 (Client): Run 'PYTHONPATH=src python -m tx2tx.client.main --server <server-ip>:24800'"
echo ""
echo "==================================================================="
echo ""

cd /data/data/com.termux/files/home/src/tx2tx

echo "Starting server..."
PYTHONPATH=src python -m tx2tx.server.main --config config.yml --port 24800 &
SERVER_PID=$!

echo "Server PID: $SERVER_PID"
echo ""
echo "Waiting 2 seconds for server to initialize..."
sleep 2

echo ""
echo "Server is running. Move your cursor to the edge of the screen!"
echo "Watch the log output below for boundary detection."
echo ""
echo "Press Ctrl+C to stop the test."
echo "==================================================================="
echo ""

# Wait for user interrupt
wait $SERVER_PID
