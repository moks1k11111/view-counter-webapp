#!/bin/bash
# Startup script for Railway deployment

# Use PORT from environment, default to 8080 if not set
PORT="${PORT:-8080}"

# Start uvicorn with the PORT
exec uvicorn api:app --host 0.0.0.0 --port "$PORT"
