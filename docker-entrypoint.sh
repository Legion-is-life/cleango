#!/bin/sh
set -e

# Ensure config directory exists and has correct permissions
mkdir -p /config
touch /config/cleango.db
chmod 666 /config/cleango.db

# Execute the command passed to docker run
exec "$@"
