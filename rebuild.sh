#!/bin/bash
# Rebuild the LGAC Virtual Assistant container
set -e

cd "$(dirname "$0")"

echo "Stopping existing containers..."
docker-compose down 2>/dev/null || true

echo "Building fresh container..."
docker-compose up -d --build --no-cache

echo "Done. Container is running at http://localhost:8000"
echo "Logs: docker-compose logs -f"
