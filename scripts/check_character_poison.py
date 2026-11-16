"""Unknown schema → DLQ; следующий нормальный факт продолжает обрабатываться. Только test."""
import json
import subprocess
import time
import uuid
from pathlib import Path
import httpx
from character_test_stack import environment,PROJECT

env=environment();cfg=json.loads(Path('.secrets/character-test/test-owner.json').read_text());base='http://127.0.0.1:28083'
def api(service,path,method='GET',data=None):
    prefix='/api/character/v1/' if service=='character' else '/api/v1/'+service+'/'
    r=httpx.request(method,base+prefix+path,json=data,headers={'Authorization':'Bearer '+cfg['tokens'][service]},timeout=10);r.raise_for_status();return r.json()
def docker(service,code):
    r=subprocess.run(['docker','compose','exec','-T',service,'python','-c',code],env=env,text=True,capture_output=True,check=True);return r.stdout.strip()
query="""import asyncio,json,aio_pika
from pathlib import Path
async def main():
 c=json.loads(Path('/run/secrets/config').read_text());connection=await aio_pika.connect(c['amqp_url'])
 async with connection:
  ch=await connection.channel();q=await ch.get_queue('character.dlq');print(q.declaration_result.message_count)
asyncio.run(main())"""
def dlq_count():
    # Runtime principal намеренно не читает DLQ: это операторское свидетельство.
    r=subprocess.run(['docker','compose','exec','-T','rabbitmq','rabbitmqctl','list_queues','-p','study','-t','10','name','messages','--formatter=json'],env=env,text=True,capture_output=True,check=True)
    rows=json.loads(r.stdout[r.stdout.index('['):]);return next(x['messages'] for x in rows if x['name']=='character.dlq')
before=dlq_count();bad_id=str(uuid.uuid4())
code="""import asyncio,json,aio_pika
from pathlib import Path
async def main():
 c=json.loads(Path('/run/secrets/config').read_text());connection=await aio_pika.connect(c['amqp_url'])
 async with connection:
  ch=await connection.channel(publisher_confirms=True);ex=await ch.get_exchange('study.events')
  await ex.publish(aio_pika.Message(json.dumps({'schema_version':999,'event_id':BAD_ID}).encode(),delivery_mode=aio_pika.DeliveryMode.PERSISTENT),routing_key='practice.character-evidence.changed.v1',mandatory=True)
asyncio.run(main())""".replace('BAD_ID',repr(bad_id))
docker('practice',code);deadline=time.monotonic()+15
while True:
    after=dlq_count()
    if after==before+1:break
    if time.monotonic()>deadline:raise AssertionError('Poison не попал в DLQ')
    time.sleep(.3)
# Настоящий источник пишет новый факт после poison, а не тестовый XP endpoint.
current=api('practice','current')['attempt']
if not current:
    cat=api('content','catalog');current=api('practice','attempts','POST',dict(command_id=str(uuid.uuid4()),problem_id=cat['problems'][0]['id'],content_release_id=cat['content_release_id']))
result=api('practice','attempts/'+current['id'],'PATCH',dict(command_id=str(uuid.uuid4()),expected_revision=current['revision'],state='abandoned'))
seq=result['learning_input_seq'];deadline=time.monotonic()+15
while True:
    summary=api('character','me/summary?at_least_practice_seq='+str(seq))
    if summary['freshness']=='current':break
    if time.monotonic()>deadline:raise AssertionError('Consumer не продолжил поток после poison')
    time.sleep(.2)
report={'status':'passed','project':PROJECT,'poison_event_id':bad_id,'dlq_before':before,'dlq_after':after,'next_practice_seq':seq,'next_fact_consumed':True}
Path('.private/evidence/crucible-v3/poison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
