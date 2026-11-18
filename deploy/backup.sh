#!/usr/bin/env bash
# ACCORD only: do not source .env or select the legacy deploy namespace.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
umask 077
exec python3 "$ROOT/scripts/accord_backup.py" backup "$@"
