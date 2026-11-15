"""Отдельная конфигурация четырёх пар primary/standby и quorum-брокера."""
import json
import os
import secrets
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from database_topology import OWNERS, database_host
from ops import host_owned

root = Path('.secrets')
out = root/'assessment'
required = {p.name for p in root.glob('*.json')} | {'erlang-cookie'}
required |= {f'replication-{o}-password' for o in OWNERS}
required |= {f'postgres-{o}-init.sql' for o in OWNERS}
if out.exists() and (out/'postgres-content-init.sql').is_file():
    missing = sorted(name for name in required if not (out/name).is_file())
    if missing:
        raise SystemExit('Неполная конфигурация assessment: '+', '.join(missing))
    for p in out.glob('*.json'):
        json.loads(p.read_text())
    for owner in OWNERS:
        config = json.loads((out/(owner+'.json')).read_text())
        if config['dsn'] != database_host(config['dsn'], owner, replicated=True):
            raise SystemExit('Несовместимая топология assessment; файлы сохранены')
    print('Существующая конфигурация assessment проверена и сохранена.')
    raise SystemExit(0)
if out.exists():
    archive = Path('.private')/('assessment-config-before-db-split-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(out, archive)
    archive.chmod(0o700)
    host_owned(archive)
with tempfile.TemporaryDirectory(prefix='.assessment-', dir=root) as temp:
    stage = Path(temp)
    for p in root.glob('*.json'):
        data = json.loads(p.read_text())
        if 'base_url' in data: data['base_url'] = 'http://localhost:18081'
        if 'origin' in data: data['origin'] = 'http://localhost:18081'
        if p.stem in OWNERS:
            data['dsn'] = database_host(data['dsn'], p.stem, replicated=True)
        if p.name == 'migrations.json':
            for owner, target in data.items():
                target['dsn'] = database_host(target['dsn'], owner, replicated=True)
        if 'amqp_url' in data:
            data['amqp_urls'] = [data['amqp_url'], data['amqp_url'].replace('@rabbitmq:', '@rabbitmq2:'), data['amqp_url'].replace('@rabbitmq:', '@rabbitmq3:')]
        (stage/p.name).write_text(json.dumps(data, indent=2))
    for owner in OWNERS:
        password = secrets.token_hex(24)
        (stage/f'replication-{owner}-password').write_text(password)
        (stage/f'postgres-{owner}-init.sql').write_text((root/f'postgres-{owner}-init.sql').read_text()+f"\nCREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD '{password}';\n")
    (stage/'erlang-cookie').write_text((out/'erlang-cookie').read_text() if (out/'erlang-cookie').is_file() else secrets.token_hex(24))
    out.mkdir(mode=0o700, exist_ok=True)
    host_owned(out)
    for p in stage.iterdir():
        p.chmod(0o644)
        host_owned(p)
        os.replace(p, out/p.name)
print('Создана конфигурация четырёх независимых пар PostgreSQL; личная история не импортируется.')
