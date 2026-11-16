"""Настоящий HTTP/outbox/RabbitMQ trace исключительно на отдельном test project."""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
import httpx
from character_test_stack import environment,PROJECT,SECRETS

if PROJECT!='crucible-character-test':raise SystemExit('Нужен отдельный синтетический project')
env=environment()
client=json.loads((SECRETS/'test-owner.json').read_text());base=client['base_url']
trace={'profile':'isolated synthetic owner','project':PROJECT,'checks':{}}


def compose(*args,input=None):
    r=subprocess.run(['docker','compose',*args],env=env,text=True,input=input,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr[-1500:])
    return r.stdout


def api(service,path,method='GET',payload=None,command=True):
    prefix='/api/character/v1/' if service=='character' else '/api/v1/'+service+'/'
    if payload is not None and command:payload={'command_id':str(uuid.uuid4()),**payload}
    r=httpx.request(method,base+prefix+path,json=payload,headers={'Authorization':'Bearer '+client['tokens'][service]},timeout=10)
    r.raise_for_status();return r.json()


def until(work,predicate,seconds=35):
    deadline=time.monotonic()+seconds
    while True:
        try:
            result=work()
            if predicate(result):return result
        except httpx.HTTPError:pass
        if time.monotonic()>deadline:raise RuntimeError('Projection did not converge')
        time.sleep(.25)


def own_sql(service,code):
    return json.loads(compose('exec','-T',service,'python','-c',code))


initial=api('character','me/summary')['xp']
catalog=api('content','catalog')
seen={a['problem_id'] for a in api('practice','attempts')['attempts']}
problem=next(p for p in catalog['problems'] if p['level']=='B' and p['id'] not in seen)
current=api('practice','current')['attempt']
if current and current['state'] in ('running','paused'):
    api('practice','attempts/'+current['id'],'PATCH',{'expected_revision':current['revision'],'state':'abandoned'})
a=api('practice','attempts','POST',{'problem_id':problem['id'],'content_release_id':catalog['content_release_id']})
attempt_id=a['id'];trace['attempt_id']=attempt_id
compose('stop','-t','10','character')
try:
    a=api('practice','attempts/'+attempt_id,'PATCH',{'expected_revision':a['revision'],'draft':'Synthetic acceptance trace. The mathematical self-assessment is a test fixture.'})
    a=api('practice','attempts/'+attempt_id+'/complete','POST',{'expected_revision':a['revision'],
        'part_outcomes':[{'part_id':p['id'],'outcome':'independent','quality':1} for p in a['problem']['parts']],
        'reflection':'Synthetic acceptance only; never import into a personal profile.'})
    trace['correlation_id']=a['character_operation_id'];trace['checks']['save_during_outage']='passed'
    trace['queue_backlog']=compose('exec','-T','rabbitmq','rabbitmqctl','list_queues','-p','study','name','messages_ready').strip()
finally:
    compose('start','character')
    subprocess.run(['scripts/firewall','apply'],env=env,check=True,capture_output=True)
summary=until(lambda:api('character','me/summary'),lambda s:s['source_checkpoints'].get('practice-service',0)>=a['learning_input_seq'])
expected_gain=80 if initial==0 else summary['xp']-initial
trace['after_award']=summary['xp'];trace['checks']['backlog_recovered']='passed'
source=own_sql('practice',f'''import json
from pathlib import Path
from platformkit.runtime import db
c=json.loads(Path('/run/secrets/config').read_text())
with db(c) as conn:
 r=conn.execute("SELECT event_id,event FROM outbox WHERE event->>'aggregate_id'=%s AND event->'payload'->>'attempt_status'='completed' ORDER BY created_at DESC LIMIT 1",({attempt_id!r},)).fetchone()
 print(json.dumps({{'event_id':str(r['event_id']),'event':r['event']}}))''')
trace['original_event_id']=source['event_id']
duplicate=own_sql('practice',f'''import json,uuid
from pathlib import Path
from platformkit.runtime import db,emit
c=json.loads(Path('/run/secrets/config').read_text())
with db(c) as conn:
 e=conn.execute('SELECT event FROM outbox WHERE event_id=%s',({source['event_id']!r},)).fetchone()['event']
 corr=str(uuid.uuid4());seq=emit(conn,c,e['event_type'],e['profile_id'],e['aggregate_id'],e['aggregate_revision'],e['payload'],corr)
 r=conn.execute("SELECT event_id FROM outbox WHERE event->>'correlation_id'=%s",(corr,)).fetchone()
 print(json.dumps({{'seq':seq,'event_id':str(r['event_id'])}}))''')
trace['duplicate_event_id']=duplicate['event_id']
s=until(lambda:api('character','me/summary'),lambda s:s['source_checkpoints'].get('practice-service',0)>=duplicate['seq'])
assert s['xp']==summary['xp'];trace['checks']['different_event_same_fact']='passed'
proposal=api('practice','attempts/'+attempt_id+'/proposals','POST',{'expected_revision':a['revision'],'outcome':'assisted','reason':'Synthetic correction: assistance was omitted from the original fixture.'})
a=api('practice','proposals/'+proposal['proposal_id']+'/approve','POST',{})
s=until(lambda:api('character','me/summary'),lambda s:s['source_checkpoints'].get('practice-service',0)>=a['learning_input_seq'])
trace['after_correction']=s['xp'];assert s['xp']==summary['xp']-24
trace['checks']['compensating_delta']='passed'
ledger=own_sql('character','''import json
from pathlib import Path
from platformkit.runtime import db
c=json.loads(Path('/run/secrets/config').read_text())
with db(c) as conn:
 rows=conn.execute('SELECT business_key,delta,source_revision,correlation_id FROM xp_ledger ORDER BY id').fetchall()
 print(json.dumps(rows,default=str))''')
trace['ledger']=ledger
trace['checks']['ledger_matches_summary']='passed' if sum(r['delta'] for r in ledger)==s['xp'] else 'failed'
assert trace['checks']['ledger_matches_summary']=='passed'
out=Path('.private/evidence/crucible-v3/event-flow.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks':trace['checks'],'evidence':str(out),'before':initial,'awarded':summary['xp'],'corrected':s['xp']},ensure_ascii=False))
