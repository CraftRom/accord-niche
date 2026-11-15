#!/usr/bin/env bash
# Safe entrypoint for the domain stack. Never evaluates dotenv values as shell code.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
umask 077
edge=0
if [[ ${1:-} == --docker-edge ]]; then edge=1; shift; fi
if [[ $# == 0 ]]; then
    echo 'Використання: bash deploy/domains.sh [--docker-edge] up -d --build | ps | logs --tail=100 | check'
    exit 0
fi
python3 scripts/setup_domains.py --check
if [[ $1 == check ]]; then exit 0; fi
# Compose interpolation must use the same checked credentials and port settings.
unset POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REDIS_PASSWORD
unset ACCORD_SITE_PORT ACCORD_DASHBOARD_PORT ACCORD_MINIAPP_PORT
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES
compose=(docker compose --env-file "$ROOT/.env.domains" -f "$ROOT/deploy/docker-compose.domains.yml")
if [[ $edge == 1 ]]; then
    compose+=(-f "$ROOT/deploy/docker-compose.edge-network.yml")
fi
# Prevent accidental bypass of the checked files, namespace or fixed listeners.
for arg in "$@"; do
    case "$arg" in
        -f|-f?*|--file|--file=*|-p|-p?*|--project-name|--project-name=*|--env-file|--env-file=*|--project-directory|--project-directory=*|-v|-v?*|--volumes|--volumes=*)
            echo 'Зміна Compose namespace/файлів або видалення томів через цей сценарій заборонені.' >&2
            exit 2 ;;
    esac
done
"${compose[@]}" config --quiet
exec "${compose[@]}" "$@"
