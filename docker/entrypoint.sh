#!/bin/bash
set -e

echo "--- 🐱 Cheshire Cat Boot Sequence ---"

if [ -d "./cat/plugins" ]; then
    echo "Checking dependencies in the installed plugins..."
    find ./cat/plugins -name requirements.txt | sed 's/^/-r /' | xargs -r uv pip install --no-cache --no-upgrade
    echo "Plugin dependencies verified."
fi

uv cache clean
rm -rf /tmp/* /var/tmp/*

echo "--- 🐱 Starting Cheshire Cat ---"

exec "$@"