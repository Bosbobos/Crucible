import json
from datetime import datetime, timezone
from ops import compose, evidence

results=[]
for owner in ['content','practice','learning','reports']:
    code='''import json,psycopg
from pathlib import Path
from psycopg.conninfo import make_conninfo
c=json.loads(Path('/run/secrets/config').read_text())
results=[]
for target in ['content','practice','learning','reports']:
 try:
  with psycopg.connect(make_conninfo(c['dsn'],dbname=target+'_db'),connect_timeout=2) as conn:
   role=conn.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]
   assert not role
   results.append({'target':target,'connected':True})
 except psycopg.OperationalError:
  results.append({'target':target,'connected':False})
print(json.dumps(results))'''
    checks=json.loads(compose('exec','-T',owner,'python','-c',code).stdout)
    for item in checks:
        assert item['connected']==(owner==item['target']),(owner,item)
    results.append({'owner':owner,'checks':checks})
code='''import json,psycopg,uuid
from pathlib import Path
c=json.loads(Path('/run/secrets/config').read_text())
with psycopg.connect(c['dsn']) as conn:
 id=str(uuid.uuid4());conn.execute('INSERT INTO plan_drafts VALUES (%s,%s)',(id,'synthetic'))
 conn.execute('UPDATE plan_drafts SET title=%s WHERE id=%s',('updated',id))
 assert conn.execute('SELECT title FROM plan_drafts WHERE id=%s',(id,)).fetchone()[0]=='updated'
 conn.execute('DELETE FROM plan_drafts WHERE id=%s',(id,))
 assert conn.execute('SELECT count(*) FROM plan_drafts WHERE id=%s',(id,)).fetchone()[0]==0
print('INSERT SELECT UPDATE DELETE passed')'''
print(compose('exec','-T','learning','python','-c',code).stdout.strip())
evidence('sql-isolation',{'at':datetime.now(timezone.utc),'results':results,'crud':'passed on ephemeral plan draft'})
print('4 allowed own-DB connections; 12 denied cross-DB connections; no superusers.')
