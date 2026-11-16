"""Coordinated owner-DB backup, AES-GCM encrypted with a separately stored local key."""
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from platformkit.backup_format import encrypt_backup, SUFFIX
from ops import COMPOSE, compose, evidence, host_owned, refresh_firewall, writable_databases

if os.getenv('CRUCIBLE_DEMO')!='1':raise SystemExit('This initial workflow is restricted to the synthetic stack: CRUCIBLE_DEMO=1')
names=['content','practice','learning','reports','character']
apps=['web',*names]
folder=Path('.private/backups');folder.mkdir(parents=True,exist_ok=True)
key_path=Path('.secrets/backup-key')
if not key_path.exists():key_path.write_bytes(os.urandom(32));key_path.chmod(0o600);host_owned(key_path)
key=key_path.read_bytes()
started=datetime.now(timezone.utc)
primaries=writable_databases()


def counts():
    result={}
    for name in names:
        service=primaries[name]
        query="SELECT string_agg(format('SELECT %L AS table_name, count(*) AS count FROM %I;', tablename, tablename), ' ') FROM pg_tables WHERE schemaname='public'"
        queries=compose('exec','-T',service,'psql','-U','postgres','-d',name+'_db','-Atc',query).stdout.strip()
        result[name]=sorted(compose('exec','-T',service,'psql','-U','postgres','-d',name+'_db','-Atc',queries).stdout.strip().splitlines())
    return result


try:
    compose('stop','-t','20',*apps)
    manifest={'schema_version':2,'kind':'synthetic-coordinated-backup','created_at':started.isoformat(),
              'databases':names,'source_primaries':primaries,'tables':counts(),'files':{},
              'consistency':'All HTTP writers, publishers and consumers stopped before any dump',
              'off_device_copy':False}
    with tempfile.TemporaryDirectory(prefix='crucible-backup-') as temp:
        root=Path(temp)
        for name in names:
            path=root/(name+'.dump')
            with path.open('wb') as stream:
                subprocess.run(COMPOSE+['exec','-T',primaries[name],'pg_dump','-U','postgres','-d',name+'_db','-Fc','--no-owner'],stdout=stream,check=True)
            manifest['files'][path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w:gz') as tar:
            for p in sorted(root.iterdir()):tar.add(p,arcname=p.name)
        path=folder/(started.strftime('%Y%m%dT%H%M%SZ')+SUFFIX)
        path.write_bytes(encrypt_backup(archive.getvalue(), key))
        path.chmod(0o600)
        host_owned(path)
    evidence('backup',{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'manifest':manifest,'seconds':(datetime.now(timezone.utc)-started).total_seconds()})
    print(str(path))
finally:
    compose('start',*apps)
    refresh_firewall()
