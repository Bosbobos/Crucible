"""Репетиция feature flags на изолированном синтетическом стенде, без down данных."""
import json
import subprocess
import time
import uuid
from pathlib import Path
import httpx
from character_test_stack import environment,PROJECT

env=environment();path=Path('.secrets/character-test/character.json');original=path.read_bytes()
cfg=json.loads(Path('.secrets/character-test/test-owner.json').read_text());base='http://127.0.0.1:28083'
def api(service,endpoint,method='GET',data=None,expected=200):
 prefix='/api/character/v1/' if service=='character' else '/api/v1/'+service+'/'
 r=httpx.request(method,base+prefix+endpoint,json=data,headers={'Authorization':'Bearer '+cfg['tokens'][service]},timeout=10)
 assert r.status_code==expected,(r.status_code,r.text);return r.json()
def restart():
 subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','character'],env=env,check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['scripts/firewall','apply'],env=env,check=True,stdout=subprocess.DEVNULL)
 for _ in range(50):
  try:
   # К HTTP readiness можно перейти после собственной DB и запуска приложения.
   r=httpx.get(base+'/api/character/v1/me/summary',headers={'Authorization':'Bearer '+cfg['tokens']['character']},timeout=3)
   if r.status_code in (200,503):return
  except httpx.HTTPError:pass
  time.sleep(.2)
 raise AssertionError('API не запустился')
try:
 before=api('character','me/summary');disabled=json.loads(original);disabled.update(character_read=False,character_write=False);path.write_text(json.dumps(disabled,indent=2));restart()
 api('character','me/summary',expected=503)
 api('character','me/preferences','PATCH',dict(command_id=str(uuid.uuid4()),expected_revision=1,rpg_visible=True,focus_mode=False),expected=503)
 cat=api('content','catalog');a=api('practice','current')['attempt']
 if a:api('practice','attempts/'+a['id'],'PATCH',dict(command_id=str(uuid.uuid4()),expected_revision=a['revision'],state='abandoned'))
 p=cat['problems'][0];a=api('practice','attempts','POST',dict(command_id=str(uuid.uuid4()),problem_id=p['id'],content_release_id=cat['content_release_id']))
 a=api('practice','attempts/'+a['id'],'PATCH',dict(command_id=str(uuid.uuid4()),expected_revision=a['revision'],draft='Synthetic rollback rehearsal: study save remains available.'))
 a=api('practice','attempts/'+a['id'],'PATCH',dict(command_id=str(uuid.uuid4()),expected_revision=a['revision'],state='abandoned'));seq=a['learning_input_seq']
finally:
 path.write_bytes(original);restart()
deadline=time.monotonic()+20
while True:
 after=api('character','me/summary?at_least_practice_seq='+str(seq))
 if after['freshness']=='current':break
 if time.monotonic()>deadline:raise AssertionError('Backlog не восстановлен после flags rollback')
 time.sleep(.2)
assert after['xp']==before['xp']
report=dict(status='passed',project=PROJECT,disabled_read=503,disabled_write=503,practice_save=200,writer_disabled_by_stopping_subscription=True,backlog_recovered_to=seq,xp_preserved=after['xp'],destructive_down=False)
Path('.private/evidence/crucible-v3/rollback.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
