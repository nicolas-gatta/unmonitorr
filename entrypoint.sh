#!/bin/bash
set -e

# PUID/PGID let anyone deploying this container choose whatever user/group
# the host-side data folder is owned by - the container adapts to match,
# instead of forcing everyone to match a UID baked into the image.
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

CURRENT_UID="$(id -u appuser)"
CURRENT_GID="$(id -g appuser)"

if [ "$PUID" != "$CURRENT_UID" ]; then
    usermod -o -u "$PUID" appuser
fi

if [ "$PGID" != "$CURRENT_GID" ]; then
    groupmod -o -g "$PGID" appuser
fi

mkdir -p /app/data
chown -R appuser:appuser /app/data

# Drop from root to appuser (now remapped to PUID:PGID) before running the app
exec gosu appuser "$@"