#!/usr/bin/env bash
# Start ngrok and wire the public URL into Docker containers.
set -euo pipefail

PUBLIC_URL="https://bunkhouse-brush-humid.ngrok-free.dev"

echo "Starting ngrok..."
pkill -f "ngrok start" 2>/dev/null || true
sleep 1
ngrok start --all &
sleep 4

echo ""
echo "============================================"
echo "  Public URL: $PUBLIC_URL"
echo "============================================"
echo ""
echo "Share this with testers: $PUBLIC_URL"
echo "GitHub OAuth callback:   $PUBLIC_URL/auth/callback"
echo ""

# Restart containers with public URL env vars
PUBLIC_API_URL="$PUBLIC_URL" UI_BASE_URL="$PUBLIC_URL" \
  docker compose up -d --no-build api ui nginx

echo "Done! Testers can open: $PUBLIC_URL"
echo "Press Ctrl+C to stop ngrok."
wait
