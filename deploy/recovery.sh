#!/usr/bin/env bash
# Full ACCORD recovery bundles; the older restore.sh remains database-only.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
umask 077
exec python3 "$ROOT/scripts/accord_recovery.py" "$@"
