#!/usr/bin/env bash
# Validates a trusted custom archive and ACCORD ownership before any stop/restore.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
umask 077
exec python3 "$ROOT/scripts/accord_backup.py" restore "$@"
