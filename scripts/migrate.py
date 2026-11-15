"""Versioned, checksummed migrations, using isolated migration credentials."""
import hashlib
import json
import os
from pathlib import Path
import psycopg

settings = json.loads(Path(os.environ.get('CRUCIBLE_MIGRATIONS', '/run/secrets/migrations')).read_text())
for name, target in settings.items():
    with psycopg.connect(target['dsn'], connect_timeout=5) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
        for path in sorted((Path('migrations')/name).glob('[0-9]*.sql')):
            text = path.read_text()
            checksum = hashlib.sha256(text.encode()).hexdigest()
            row = conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s', (path.name,)).fetchone()
            if row:
                if row[0] != checksum:
                    raise RuntimeError(f'Applied migration changed: {name}/{path.name}')
                continue
            conn.execute(text)
            conn.execute('INSERT INTO schema_migrations VALUES (%s,%s,now())', (path.name, checksum))
        from psycopg import sql
        conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(target['runtime_role'])))
        conn.execute(sql.SQL('REVOKE ALL ON schema_migrations FROM {}').format(sql.Identifier(target['runtime_role'])))
    print(f'{name}: migrations applied')
