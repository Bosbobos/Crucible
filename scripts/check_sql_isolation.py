"""Раздельные свидетельства runtime SQL-прав и межсервисной сетевой изоляции."""
import json
from datetime import datetime, timezone
from database_topology import OWNERS, primary
from ops import compose, evidence, run, writable_databases

nodes = writable_databases()
addresses = {}
for owner, node in nodes.items():
    cid = compose('ps', '-q', node).stdout.strip()
    metadata = json.loads(run(['docker', 'inspect', cid]).stdout)[0]
    addresses[owner] = next(value['IPAddress'] for name, value in metadata['NetworkSettings']['Networks'].items() if name.endswith('_'+owner+'_storage'))
results = []
for owner in OWNERS:
    code = '''import json,psycopg,socket
from pathlib import Path
from psycopg.conninfo import make_conninfo
c=json.loads(Path('/run/secrets/config').read_text())
with psycopg.connect(c['dsn'],connect_timeout=3) as conn:
 role=conn.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
 assert role==(False,False,False)
 assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
 assert not conn.execute("SELECT has_database_privilege(current_user,'postgres','CONNECT')").fetchone()[0]
 own_db=conn.execute('SELECT current_database()').fetchone()[0]
 assert own_db==OWNER+'_db'
try:
 with psycopg.connect(make_conninfo(c['dsn'],dbname='postgres'),connect_timeout=3): pass
except psycopg.OperationalError:
 maintenance_denied=True
else: raise AssertionError('Unexpected CONNECT to maintenance database')
checks=[]
for target,address in ADDRESSES.items():
 with socket.socket() as sock:
  sock.settimeout(2);connected=sock.connect_ex((address,5432))==0
 assert connected==(OWNER==target),(OWNER,target,connected)
 checks.append({'target':target,'connected':connected,'expected':OWNER==target})
print(json.dumps({'owner':OWNER,'database':own_db,'runtime_privileges_restricted':True,'maintenance_db_denied':maintenance_denied,'tcp_checks':checks}))'''
    code = 'OWNER='+repr(owner)+'\nADDRESSES='+repr(addresses)+'\n'+code
    checks = json.loads(compose('exec', '-T', owner, 'python', '-c', code).stdout)
    # Администратор проверяет сам состав инстанса, не передавая его пароль приложению.
    inventory = compose('exec', '-T', nodes[owner], 'psql', '-U', 'postgres', '-Atc',
                        "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname<>'postgres' ORDER BY datname").stdout.splitlines()
    assert inventory == [owner+'_db'], (owner, inventory)
    roles = compose('exec', '-T', nodes[owner], 'psql', '-U', 'postgres', '-Atc',
                    "SELECT rolname FROM pg_roles WHERE rolname LIKE '%\\_runtime' OR rolname LIKE '%\\_migration' ORDER BY rolname").stdout.splitlines()
    assert roles == [owner+'_migration', owner+'_runtime'], (owner, roles)
    checks['instance_databases'] = inventory
    checks['instance_roles'] = roles
    results.append(checks)
code = '''import json,uuid
from pathlib import Path
from platformkit.runtime import db
c=json.loads(Path('/run/secrets/config').read_text())
with db(c) as conn:
 id=str(uuid.uuid4());conn.execute('INSERT INTO plan_drafts VALUES (%s,%s)',(id,'synthetic'))
 conn.execute('UPDATE plan_drafts SET title=%s WHERE id=%s',('updated',id))
 assert conn.execute('SELECT title FROM plan_drafts WHERE id=%s',(id,)).fetchone()['title']=='updated'
 conn.execute('DELETE FROM plan_drafts WHERE id=%s',(id,))
 assert conn.execute('SELECT count(*) AS count FROM plan_drafts WHERE id=%s',(id,)).fetchone()['count']==0
print('INSERT SELECT UPDATE DELETE passed')'''
print(compose('exec', '-T', 'learning', 'python', '-c', code).stdout.strip())
evidence('sql-isolation', {'at': datetime.now(timezone.utc), 'topology': 'one-postgres-container-per-service',
                           'results': results, 'crud': 'passed on ephemeral plan draft'})
print(f'{len(OWNERS)} own DB connections passed; {len(OWNERS)*(len(OWNERS)-1)} foreign PostgreSQL TCP connections denied; runtime roles restricted.')
