from pathlib import Path

p = Path(__file__).resolve().parents[2] / "deploy" / "deploy.sh"
s = p.read_text(encoding="utf-8")
required = [
    "ФАЗА 1/5: базові сервіси",
    "ФАЗА 2/5: міграції БД",
    "ФАЗА 3/5: API",
    "ФАЗА 4/5: основні застосунки",
    "ФАЗА 5/5: nginx основного сайту",
    "Фінальний API health: OK",
]
pos = [s.index(x) for x in required]
assert pos == sorted(pos), "deploy phases are out of order"
assert "up -d --remove-orphans" not in s, "global up/remove-orphans must not return"
assert "up -d --no-deps --force-recreate nginx" in s, "nginx must be recreated after api"
assert "promo-controller" not in s, "promo pages were removed from ACCORD"
assert "rollback_core_runtime" in s
assert s.index('qa_migration_enum_backfill.py') < s.index('stop api scheduler'), "enum-migration SQL test must run before workers stop"
assert 'if ! "${COMPOSE[@]}" run --rm migrate; then' in s, "failed migration must show recovery guidance"
print("deploy phased regression: PASS")
