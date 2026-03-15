#!/bin/bash
set -e

echo "--- 🐱 Grinning Cat Boot Sequence ---"

echo "Running migrations..."
uv run python migrations/manage_migrations.py upgrade head

echo "--- 🐱 Starting Grinning Cat ---"

exec "$@"