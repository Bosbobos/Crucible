"""Dry-run через согласованный owner export. Ничего не записывает в RPG."""
import argparse
import hashlib
import json
import time
import uuid
from collections import Counter
from pathlib import Path
import httpx
from contracts.character import attempt_snapshot
from character_service.definitions import CATALOG_VERSION,RULESET
from character_service.domain import recompute
from character_service.store import validate_fact

parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=Path('.secrets/operator.json'));args=parser.parse_args()
client=json.loads(args.config.read_text());base=client['base_url']


def api(service,path,method='GET',body=None):
    prefix='/api/character/v1/' if service=='character' else '/api/v1/'+service+'/'
    r=httpx.request(method,base+prefix+path,json=body,headers={'Authorization':'Bearer '+client['tokens'][service]},timeout=10)
    r.raise_for_status();return r.json()


job=api('reports','jobs','POST',{'command_id':str(uuid.uuid4())})
deadline=time.monotonic()+45
while True:
    state=api('reports','jobs/'+job['job_id'])
    if state['status']=='ready':break
    if time.monotonic()>deadline:raise SystemExit('Экспорт не готов; dry-run не выполнялся')
    time.sleep(.3)
artifact=api('reports','jobs/'+job['job_id']+'/artifact')['artifact']
snapshot=artifact['practice'];facts=[];gaps=Counter()
for a in snapshot['attempts']:
    if a['state']!='completed':gaps['not_completed']+=1;continue
    fact=attempt_snapshot(a)
    if fact is None:gaps['missing_confirmed_reward_snapshot']+=1;continue
    try:validate_fact(fact)
    except ValueError:gaps['invalid_reward_snapshot']+=1;continue
    facts.append(fact)
projected=recompute(facts)
current=api('character','me/summary')
report={'status':'dry_run','writes_to_character':0,'source':'reports owner export; repeatable practice snapshot + cursor',
    'source_practice_checkpoint':snapshot['practice_seq'],'attempts':len(snapshot['attempts']),
    'eligible_facts':len(facts),'gaps':dict(gaps),'projected_xp_without_legacy_addition':projected['xp'],
    'current_confirmed_xp':current['xp'],'ruleset_version':RULESET,'catalog_version':CATALOG_VERSION,
    'source_hash':hashlib.sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest(),
    'live_replay_performed':False,'owner_cutover_required':projected['xp']!=current['xp'],
    'legacy_xp_writer_found':False,'notification_replay':False}
path=Path('.private/evidence/crucible-v3/import-preview.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
