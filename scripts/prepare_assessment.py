import json
import secrets
import os
from pathlib import Path
from ops import host_owned

root=Path('.secrets')
out=root/'assessment'
if out.exists():
    required={p.name for p in root.glob('*.json')}|{'replication-password','erlang-cookie','postgres-init.sql'}
    missing=sorted(name for name in required if not (out/name).is_file())
    if missing:raise SystemExit('Неполная конфигурация assessment: '+', '.join(missing))
    for p in out.glob('*.json'):json.loads(p.read_text())
    print('Существующая конфигурация assessment проверена и сохранена.')
    raise SystemExit(0)
out.mkdir(mode=0o700,exist_ok=False)
host_owned(out)
for p in root.glob('*.json'):
    data=json.loads(p.read_text())
    if 'base_url' in data:data['base_url']='http://localhost:18081'
    if 'origin' in data:data['origin']='http://localhost:18081'
    if 'dsn' in data:data['dsn']=data['dsn'].replace('@postgres:5432/','@postgres:5432,standby:5432/')+'?target_session_attrs=read-write&connect_timeout=2'
    if p.name=='migrations.json':
        for target in data.values():
            target['dsn']=target['dsn'].replace('@postgres:5432/','@postgres:5432,standby:5432/')+'?target_session_attrs=read-write&connect_timeout=2'
    if 'amqp_url' in data:data['amqp_urls']=[data['amqp_url'],data['amqp_url'].replace('@rabbitmq:', '@rabbitmq2:'),data['amqp_url'].replace('@rabbitmq:', '@rabbitmq3:')]
    (out/p.name).write_text(json.dumps(data,indent=2));(out/p.name).chmod(0o600)
replication_password=secrets.token_hex(24)
(out/'replication-password').write_text(replication_password)
(out/'erlang-cookie').write_text(secrets.token_hex(24))
(out/'postgres-init.sql').write_text((root/'postgres-init.sql').read_text()+f"\nCREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD '{replication_password}';\n")
for p in out.iterdir():p.chmod(0o644);host_owned(p)
print('Isolated synthetic assessment configuration created; no personal history imported.')
