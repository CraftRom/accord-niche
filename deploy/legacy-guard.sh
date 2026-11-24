# Sourced by the ELFAR-era scripts kept in deploy/ (deploy.sh, bootstrap.sh,
# certbot-init.sh, render-nginx.sh, repair-main-domain.sh,
# update-cloudflare-ips.sh). They drive deploy/docker-compose.prod.yml, which
# publishes 80/443 and uses ELFAR's service names. On the shared VPS ACCORD
# runs only through deploy/domains.sh; ELFAR itself lives in /opt/elfar.
_legacy_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
_elfar_dir="${ELFAR_DEPLOY_DIR:-/opt/elfar/deploy}"
if [[ -f "$_legacy_root/.env.domains" ]] || { [[ -f "$_elfar_dir/docker-compose.prod.yml" ]] && [[ "$(cd "$_elfar_dir" && pwd -P)" != "$_legacy_root/deploy" ]]; }; then
    echo "ПОМИЛКА: $(basename "$0") — сценарій старої спільної інфраструктури ELFAR." >&2
    echo "  На цьому сервері ACCORD працює через: bash deploy/domains.sh --docker-edge up -d --build" >&2
    echo "  Цей сценарій перестворив би nginx і контейнери ELFAR (порти 80/443)." >&2
    exit 3
fi
unset _legacy_root _elfar_dir
