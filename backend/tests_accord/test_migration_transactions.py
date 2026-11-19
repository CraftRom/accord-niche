"""Enum changes must commit before later revisions consume the new value.

Set QA_POSTGRES_BIN to a PostgreSQL bin directory to also execute the generated
SQL against a temporary, real PostgreSQL cluster in single-user mode. This
requires no network sockets and never connects to an existing database.
"""
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
POSTGRES_BIN = os.environ.get('QA_POSTGRES_BIN')


def upgrade_sql(revision):
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', revision, '--sql'],
        cwd=BACKEND, env={**os.environ, 'PYTHONPATH': str(BACKEND),
                         'DATABASE_URL': 'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_new_enum_value_is_committed_before_status_backfill():
    sql = upgrade_sql('a9d4e77b1c60')
    addition = sql.index("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'ACCEPTED'")
    backfill = sql.index("UPDATE orders SET status = 'ACCEPTED'")
    assert 'COMMIT;' in sql[addition:backfill]
    assert sql[addition:backfill].count('BEGIN;') >= 1
    assert sql.count('BEGIN;') == sql.count('COMMIT;') == 8


@pytest.fixture
def postgres(tmp_path):
    if not POSTGRES_BIN:
        pytest.skip('QA_POSTGRES_BIN is required for real PostgreSQL execution')
    binaries, data = Path(POSTGRES_BIN), tmp_path / 'pgdata'
    result = subprocess.run([str(binaries / 'initdb'), '-D', str(data), '-U', 'postgres',
                             '--no-locale', '--encoding=UTF8', '--auth=trust'],
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr

    def execute(sql, expect_error=False):
        # -j reads commands through blank-line separators, preserving SQL lines.
        result = subprocess.run([str(binaries / 'postgres'), '--single', '-j',
                                 '-D', str(data), 'postgres'], input=sql + '\n\n',
                                text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        if not expect_error:
            assert not re.search(r'\b(?:ERROR|FATAL|PANIC):', result.stderr), result.stderr
        return result

    return execute


def test_real_postgres_reproduces_original_failure(postgres):
    sql = upgrade_sql('a9d4e77b1c60')
    single_transaction = 'BEGIN;\n' + sql.replace('BEGIN;', '').replace('COMMIT;', '') + '\nCOMMIT;'
    result = postgres(single_transaction, expect_error=True)
    assert 'unsafe use of new value "ACCEPTED"' in result.stderr


def test_real_postgres_fresh_database_passes_backfill(postgres):
    postgres(upgrade_sql('a9d4e77b1c60'))
    result = postgres('SELECT version_num FROM alembic_version;')
    assert 'a9d4e77b1c60' in result.stdout


def test_real_postgres_existing_order_is_preserved_and_converted(postgres):
    postgres(upgrade_sql('c7e2b8f41a09'))
    postgres("""
        INSERT INTO users (id, tg_id, age_confirmed, is_blocked, referral_code,
            bonus_balance, orders_count, total_spent, referrals_count, search_key)
        VALUES (1, 1, false, false, 'MIGRATION-QA', 0, 0, 0, 0, 'qa');
        INSERT INTO orders (id, user_id, status, subtotal, discount, bonus_used,
                            total, referral_paid, search_key)
        VALUES (1, 1, 'CONFIRMED', 100, 0, 0, 100, false, 'qa');
    """)
    postgres(upgrade_sql('c7e2b8f41a09:a9d4e77b1c60'))
    result = postgres('SELECT id, status, total FROM orders;')
    assert 'status = "ACCEPTED"' in result.stdout
    assert 'total = "100.00"' in result.stdout
    assert 'id = "1"' in result.stdout


def blog_baseline(postgres):
    # Test this additive revision against its required existing tables. Older
    # data-dependent migrations cannot all be rendered in Alembic offline mode.
    postgres("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, bonus_balance NUMERIC(12,2),
            orders_count INTEGER, total_spent NUMERIC(12,2));
        CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('bc1a8f723f9d');
    """)


def test_blog_migration_on_postgres_and_versioned_updates(postgres):
    blog_baseline(postgres)
    postgres(upgrade_sql('bc1a8f723f9d:c04b19a7e230'))
    result=postgres("""
        INSERT INTO blog_posts (slug,title,body,search_text,status,published_at,created_by,updated_by)
        VALUES ('journal','Журнал','Повний текст статті','журнал','published',now(),'owner','owner');
        INSERT INTO blog_slugs (slug,post_id) VALUES ('journal',1);
        INSERT INTO blog_comments (post_id,author_name,body,is_staff,status,client_key)
        VALUES (1,'Редакція','Відповідь',true,'approved','retry-key');
        UPDATE blog_posts SET title='Збережена версія',version=version+1 WHERE id=1 AND version=1;
        UPDATE blog_posts SET title='Застаріла версія',version=version+1 WHERE id=1 AND version=1;
        SELECT version_num FROM alembic_version;
        SELECT title,version FROM blog_posts;
    """)
    assert 'c04b19a7e230' in result.stdout
    assert 'title = "Збережена версія"' in result.stdout
    assert 'version = "2"' in result.stdout
    duplicate=postgres("INSERT INTO blog_comments (post_id,author_name,body,client_key) VALUES (1,'Другий','Дубль','retry-key');",expect_error=True)
    assert 'uq_blog_comment_retry' in duplicate.stderr
    orphan=postgres("INSERT INTO blog_comments (post_id,parent_id,author_name,body) VALUES (1,999,'Автор','Текст');",expect_error=True)
    assert 'foreign key constraint' in orphan.stderr


def test_blog_upgrade_and_downgrade_leave_existing_customers_untouched(postgres):
    blog_baseline(postgres)
    postgres("""
        INSERT INTO users (id,bonus_balance,orders_count,total_spent)
        VALUES (987,37,3,1500);
    """)
    postgres(upgrade_sql('bc1a8f723f9d:c04b19a7e230'))
    result=postgres('SELECT id,bonus_balance,orders_count,total_spent FROM users WHERE id=987;')
    assert 'bonus_balance = "37.00"' in result.stdout
    assert 'orders_count = "3"' in result.stdout
    assert 'total_spent = "1500.00"' in result.stdout
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','c04b19a7e230:bc1a8f723f9d','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres('SELECT id,bonus_balance FROM users WHERE id=987; SELECT version_num FROM alembic_version;')
    assert 'id = "987"' in result.stdout
    assert 'bc1a8f723f9d' in result.stdout


def test_catalog_import_receipts_upgrade_and_downgrade(postgres):
    blog_baseline(postgres)
    postgres(upgrade_sql('bc1a8f723f9d:d7e3a91c5b20'))
    result=postgres("""
        INSERT INTO catalog_imports (digest,created_at) VALUES ('a',now());
        SELECT version_num FROM alembic_version;
        SELECT status FROM catalog_imports;
    """)
    assert 'd7e3a91c5b20' in result.stdout and 'status = "running"' in result.stdout
    duplicate=postgres("INSERT INTO catalog_imports (digest,created_at) VALUES ('a',now());",expect_error=True)
    assert 'catalog_imports_pkey' in duplicate.stderr
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','d7e3a91c5b20:c04b19a7e230','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres("SELECT to_regclass('public.catalog_imports') IS NULL AS gone; SELECT version_num FROM alembic_version;")
    assert 'gone = "t"' in result.stdout and 'c04b19a7e230' in result.stdout


def test_token_expiry_indexes_upgrade_and_downgrade(postgres):
    blog_baseline(postgres)
    postgres("""
        CREATE TABLE website_sessions (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
        CREATE TABLE website_telegram_links (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
    """)
    postgres(upgrade_sql('bc1a8f723f9d:e2a6c4f81b37'))
    result=postgres("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_website_%_expires_at' ORDER BY 1; SELECT version_num FROM alembic_version;")
    assert 'ix_website_sessions_expires_at' in result.stdout and 'ix_website_telegram_links_expires_at' in result.stdout
    assert 'e2a6c4f81b37' in result.stdout
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','e2a6c4f81b37:d7e3a91c5b20','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres("SELECT count(*) AS n FROM pg_indexes WHERE indexname LIKE 'ix_website_%_expires_at';")
    assert 'n = "0"' in result.stdout


def test_website_visits_migration_allows_anonymous_unique_visits(postgres):
    blog_baseline(postgres)
    postgres("""
        CREATE TABLE website_sessions (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
        CREATE TABLE website_telegram_links (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
        CREATE TABLE analytics_sessions (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            session_id VARCHAR(64) NOT NULL, started_at TIMESTAMPTZ NOT NULL, attribution JSONB,
            CONSTRAINT uq_analytics_user_session UNIQUE (user_id, session_id));
        INSERT INTO users (id,bonus_balance,orders_count,total_spent) VALUES (1,0,0,0);
        INSERT INTO analytics_sessions (user_id,session_id,started_at) VALUES (1,'miniapp-old-visit',now());
    """)
    postgres(upgrade_sql('bc1a8f723f9d:f4c8e2a17d59'))
    result=postgres("""
        INSERT INTO analytics_sessions (user_id,channel,session_id,started_at) VALUES (NULL,'accord_website','web-visit-1',now());
        SELECT channel FROM analytics_sessions WHERE session_id='miniapp-old-visit';
        SELECT version_num FROM alembic_version;
    """)
    assert 'channel = "telegram_miniapp"' in result.stdout and 'f4c8e2a17d59' in result.stdout
    duplicate=postgres("INSERT INTO analytics_sessions (user_id,channel,session_id,started_at) VALUES (NULL,'accord_website','web-visit-1',now());",expect_error=True)
    assert 'ux_analytics_website_session' in duplicate.stderr
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','f4c8e2a17d59:e2a6c4f81b37','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres("SELECT count(*) AS n FROM analytics_sessions; SELECT version_num FROM alembic_version;")
    assert 'n = "1"' in result.stdout and 'e2a6c4f81b37' in result.stdout


def test_durable_import_jobs_migration_keeps_applied_receipts(postgres):
    blog_baseline(postgres)
    postgres("""
        CREATE TABLE website_sessions (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
        CREATE TABLE website_telegram_links (id INTEGER PRIMARY KEY, expires_at TIMESTAMPTZ);
        CREATE TABLE analytics_sessions (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            session_id VARCHAR(64) NOT NULL, started_at TIMESTAMPTZ NOT NULL, attribution JSONB,
            CONSTRAINT uq_analytics_user_session UNIQUE (user_id, session_id));
    """)
    postgres(upgrade_sql('bc1a8f723f9d:f4c8e2a17d59'))
    postgres("""
        INSERT INTO catalog_imports (digest,status,result,created_at) VALUES ('applied','running','{"rows":1}',now());
        INSERT INTO catalog_imports (digest,status,result,created_at) VALUES ('interrupted','running','',now());
    """)
    postgres(upgrade_sql('f4c8e2a17d59:a3d9b6e14f02'))
    result=postgres("SELECT digest,status,rows_done,attempts FROM catalog_imports ORDER BY digest; SELECT version_num FROM alembic_version;")
    assert 'digest = "applied"' in result.stdout and 'status = "done"' in result.stdout
    assert 'interrupted' not in result.stdout and 'a3d9b6e14f02' in result.stdout
    postgres("INSERT INTO catalog_imports (digest,created_at,payload,rows_total) VALUES ('queued-job',now(),'[]',0);")
    assert 'status = "queued"' in postgres("SELECT status FROM catalog_imports WHERE digest='queued-job';").stdout
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','a3d9b6e14f02:f4c8e2a17d59','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres("SELECT digest FROM catalog_imports; SELECT version_num FROM alembic_version;")
    assert 'applied' in result.stdout and 'queued-job' not in result.stdout and 'f4c8e2a17d59' in result.stdout


def test_promo_pages_are_dropped_with_their_cloudflare_credentials(postgres):
    postgres("""
        CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('a3d9b6e14f02');
        CREATE TABLE settings (key VARCHAR(64) PRIMARY KEY, value TEXT);
        INSERT INTO settings VALUES ('promo_cloudflare_api_token','enc:v1:secret'),
            ('promo_cloudflare_account_id','acc'),('shop_name','ACCORD');
        CREATE TABLE promo_landing_pages (id INTEGER PRIMARY KEY, domain VARCHAR(253));
        CREATE TABLE promo_landing_daily_stats (id INTEGER PRIMARY KEY,
            page_id INTEGER REFERENCES promo_landing_pages(id) ON DELETE CASCADE);
        INSERT INTO promo_landing_pages VALUES (1,'promo.example');
        INSERT INTO promo_landing_daily_stats VALUES (1,1);
    """)
    postgres(upgrade_sql('a3d9b6e14f02:c8f1e5a3d702'))
    result=postgres("SELECT to_regclass('public.promo_landing_pages') IS NULL AS pages_gone, "
                    "to_regclass('public.promo_landing_daily_stats') IS NULL AS stats_gone; "
                    "SELECT key FROM settings ORDER BY key; SELECT version_num FROM alembic_version;")
    assert 'pages_gone = "t"' in result.stdout and 'stats_gone = "t"' in result.stdout
    assert 'promo_cloudflare' not in result.stdout and 'key = "shop_name"' in result.stdout
    assert 'c8f1e5a3d702' in result.stdout
    downgrade=subprocess.run([sys.executable,'-m','alembic','downgrade','c8f1e5a3d702:a3d9b6e14f02','--sql'],
        cwd=BACKEND,env={**os.environ,'PYTHONPATH':str(BACKEND),'DATABASE_URL':'postgresql+asyncpg://qa:qa@localhost/qa'},
        text=True,capture_output=True,timeout=30)
    assert downgrade.returncode==0,downgrade.stderr
    postgres(downgrade.stdout)
    result=postgres("SELECT count(*) AS n FROM promo_landing_pages; SELECT version_num FROM alembic_version;")
    assert 'n = "0"' in result.stdout and 'a3d9b6e14f02' in result.stdout


def test_commerce_channel_and_queue_expressions_on_real_postgres(postgres):
    from sqlalchemy import select,func
    from sqlalchemy.dialects import postgresql
    from shop.services.commerce_workspace import channel_expression,queue_condition
    from shop import models as m
    postgres("""
        CREATE TABLE orders (id INTEGER PRIMARY KEY,status VARCHAR(32),business_state VARCHAR(16),
            tracking_number VARCHAR(64),attribution JSONB,crm_snapshot JSONB);
        INSERT INTO orders (id,status,business_state,tracking_number,attribution) VALUES
            (1,'NEW','pending',NULL,'{"source":"google","channel":"accord_website"}'),
            (2,'NEW','pending',NULL,'{"source":"accord_website","channel":"telegram_miniapp"}'),
            (3,'ACCEPTED','pending','20450000123456','{"source":"telegram_bot"}'),
            (4,'NEW','refusal',NULL,'{"source":"accord_website"}');
        INSERT INTO orders VALUES (5,'NEW','pending',NULL,NULL,'{"utm":{"source":"accord_website"}}');
    """)
    for key in ['website','miniapp','bot']:
        statement=select(func.count().label('matched')).select_from(m.Order).where(queue_condition('open'),channel_expression()==key)
        sql=str(statement.compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
        expected=2 if key=='website' else 1
        assert f'matched = "{expected}"' in postgres(sql).stdout


def test_brands_migration_moves_products_and_category_promos_on_real_postgres(postgres):
    # Minimal schema of the tables the revision reads; offline SQL must carry
    # the whole data migration because `--sql` has no rows to read.
    postgres("""
        CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('c8f1e5a3d702');
        CREATE TABLE categories (id INTEGER PRIMARY KEY, is_active BOOLEAN NOT NULL);
        CREATE TABLE subcategories (id INTEGER PRIMARY KEY, category_id INTEGER, is_active BOOLEAN NOT NULL);
        CREATE TABLE products (id INTEGER PRIMARY KEY, brand VARCHAR(100), is_active BOOLEAN NOT NULL,
            category_id INTEGER, subcategory_id INTEGER);
        CREATE TABLE promo_codes (id INTEGER PRIMARY KEY, is_active BOOLEAN NOT NULL, category_ids JSONB);
        INSERT INTO categories VALUES (1, true), (2, false), (3, true);
        INSERT INTO subcategories VALUES (10, 1, true), (11, 1, false);
        INSERT INTO products VALUES (1, '  Creed  ', true, 1, NULL), (2, 'creed', true, NULL, 10),
            (3, 'Tom   Ford', true, 2, NULL), (4, 'Kilian', true, NULL, 11), (5, '', true, NULL, NULL);
        INSERT INTO promo_codes VALUES (1, true, '[1]'), (2, true, '[3]'), (3, true, '[]'), (4, true, NULL);
    """)
    postgres(upgrade_sql('c8f1e5a3d702:e2b7c4a91d05'))
    result = postgres("""
        SELECT string_agg(name || '=' || name_key, ',' ORDER BY id) AS brands FROM brands;
        SELECT string_agg(id || ':' || coalesce(b, '-') || ':' || is_active, ',' ORDER BY id) AS products
          FROM (SELECT p.id, b.name AS b, p.is_active, p.brand FROM products p LEFT JOIN brands b ON b.id = p.brand_id) x;
        SELECT string_agg(pc.id || ':' || pc.brand_ids::text || ':' || pc.is_active, ',' ORDER BY pc.id) AS promos FROM promo_codes pc;
        SELECT version_num FROM alembic_version;
    """)
    out = result.stdout
    assert 'brands = "Creed=creed,Kilian=kilian,Tom Ford=tom ford"' in out, out
    # Creed spelled once; Tom Ford hidden by inactive category 2, Kilian by subcategory 11.
    assert 'products = "1:Creed:true,2:Creed:true,3:Tom Ford:false,4:Kilian:false,5:-:true"' in out, out
    # Category 1 holds Creed (products 1, 2) and Kilian (via subcategory 11);
    # category 3 has no products -> switched off; empty/NULL lists untouched.
    assert 'promos = "1:[1, 2]:true,2:[]:false,3:[]:true,4:[]:true"' in out, out
    assert 'e2b7c4a91d05' in out
