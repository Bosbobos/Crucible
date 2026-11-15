"""Restore into a NEW Compose project only. Existing projects/volumes are never overwritten."""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
import httpx
from datetime import datetime, timezone
from pathlib import Path
from platformkit.backup_format import decrypt_backup
from ops import run, evidence, api_base_url, host_owned, refresh_firewall
from database_topology import OWNERS, primary

parser=argparse.ArgumentParser();parser.add_argument('backup',type=Path);parser.add_argument('--project',required=True);parser.add_argument('--port',type=int,default=18082);args=parser.parse_args()
if not re.fullmatch(r'crucible-restore-[a-z0-9-]{1,35}',args.project):raise SystemExit('Project must start with crucible-restore-')
existing=run(['docker','ps','-aq','--filter','label=com.docker.compose.project='+args.project]).stdout.strip()
volumes=run(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+args.project]).stdout.strip()
if existing or volumes:raise SystemExit('Restore requires a new project with no containers or volumes')
raw=args.backup.read_bytes()
archive=decrypt_backup(raw, Path('.secrets/backup-key').read_bytes())
folder=Path('.secrets')/args.project;folder.mkdir(mode=0o700)
host_owned(folder)
for path in Path('.secrets').glob('*.json'):
    data=json.loads(path.read_text())
    if 'origin' in data:data['origin']='http://localhost:'+str(args.port)
    if 'base_url' in data:data['base_url']='http://localhost:'+str(args.port)
    target=folder/path.name;target.write_text(json.dumps(data,indent=2));target.chmod(0o644);host_owned(target)
override={'services':{'web':{'ports':[]}},'secrets':{n+'_config':{'file':str((folder/(n+'.json')).resolve())} for n in ['content','practice','learning','reports']}}
override['secrets']['operator']={'file':str((folder/'operator.json').resolve())}
override['secrets']['mcp']={'file':str((folder/'mcp.json').resolve())}
if os.getenv('CRUCIBLE_RESTORE_SUBNET_BASE'):
    import ipaddress
    prefix=os.environ['CRUCIBLE_RESTORE_SUBNET_BASE']
    network=ipaddress.ip_network(prefix+'.0.0/16')
    if not network.is_private or str(network.network_address).split('.')[:2]!=prefix.split('.'):
        raise SystemExit('CRUCIBLE_RESTORE_SUBNET_BASE должен задавать частную IPv4 /16 сеть, например 10.237')
    override['networks']={name:{'ipam':{'config':[{'subnet':prefix+'.'+str(i)+'.0/24'}]}} for i,name in enumerate(['edge','content_api','practice_api','learning_api','reports_api',*(o+'_storage' for o in OWNERS),'messages','cache'],10)}
out=Path('.private')/args.project;out.mkdir(parents=True,exist_ok=False)
# Compose's explicit override tag avoids retaining the source project's host port.
import yaml
text=yaml.safe_dump(override,sort_keys=False).replace('ports: []',f'ports: !override [127.0.0.1:{args.port}:8080]')
overlay=out/'compose.yaml';overlay.write_text(text)
base=['docker','compose','-f','compose.yaml','-f',str(overlay),'-p',args.project]
started=time.monotonic()
run(base+['up','-d','--wait',*(primary(o) for o in OWNERS)])
with tempfile.TemporaryDirectory(prefix='crucible-restore-') as temp:
    root=Path(temp)
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        members=tar.getmembers()
        if {m.name for m in members}!={'manifest.json','content.dump','practice.dump','learning.dump','reports.dump'}:raise ValueError('Unexpected archive members')
        if any(not m.isfile() or '/' in m.name for m in members):raise ValueError('Unsafe archive member')
        tar.extractall(root,filter='data')
    manifest=json.loads((root/'manifest.json').read_text())
    for name in manifest['databases']:
        path=root/(name+'.dump')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['files'][path.name]['sha256']:raise ValueError('Checksum mismatch')
        with path.open('rb') as stream:
            subprocess.run(base+['exec','-T',primary(name),'pg_restore','-U','postgres','-d',name+'_db','--exit-on-error','--clean','--if-exists','--no-owner','--role',name+'_migration'],stdin=stream,check=True)
    for name,expected in manifest['tables'].items():
        query="SELECT string_agg(format('SELECT %L AS table_name, count(*) AS count FROM %I;', tablename, tablename), ' ') FROM pg_tables WHERE schemaname='public'"
        sql=run(base+['exec','-T',primary(name),'psql','-U','postgres','-d',name+'_db','-Atc',query]).stdout.strip()
        actual=run(base+['exec','-T',primary(name),'psql','-U','postgres','-d',name+'_db','-Atc',sql]).stdout.strip().splitlines()
        assert sorted(actual)==sorted(expected),(name,actual,expected)
# Образы заранее собирает Docker CLI на хосте; оператору не нужен выход в registry.
run(base+['up','-d','--wait'])
refresh_firewall(base)
# A new broker has no copy of confirmed-but-unconsumed messages. Replay retained
# events through each owner's own dispatcher; imported receipts prevent duplicates.
replay="""import json;from pathlib import Path;from platformkit.runtime import db
cfg=json.loads(Path('/run/secrets/config').read_text())
with db(cfg) as conn: conn.execute('UPDATE outbox SET published_at=NULL')
"""
for service in ['content','practice','learning','reports']:
    run(base+['exec','-T',service,'python','-c',replay])
operator=json.loads((folder/'operator.json').read_text())
if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1':operator['base_url']=api_base_url(base)
deadline=time.monotonic()+45
while True:
    try:
        current=httpx.get(operator['base_url']+'/api/v1/practice/current',headers={'Authorization':'Bearer '+operator['tokens']['practice']},timeout=5)
        current.raise_for_status();seq=current.json()['learning_input_seq']
        progress=httpx.get(operator['base_url']+'/api/v1/learning/progress?at_least_practice_seq='+str(seq),headers={'Authorization':'Bearer '+operator['tokens']['learning']},timeout=5)
        progress.raise_for_status()
        if not progress.json()['pending']:break
    except httpx.HTTPError:pass
    if time.monotonic()>deadline:raise RuntimeError('Restored projection did not reach canonical practice cursor')
    time.sleep(.3)
evidence('restore',{'project':args.project,'port':args.port,'backup_sha256':hashlib.sha256(raw).hexdigest(),
                    'at':datetime.now(timezone.utc),'tables_verified':manifest['tables'],'seconds':time.monotonic()-started,
                    'retained_outbox_replayed':True,'applied_practice_seq':seq})
print('Restored and verified four databases in '+args.project+' at http://localhost:'+str(args.port))
