"""Lossless private staging of all legacy records. No publication and no source mutation."""
import argparse
import hashlib
import json
from pathlib import Path
import yaml

parser=argparse.ArgumentParser();parser.add_argument('backup',type=Path);args=parser.parse_args()
source=args.backup/'source';inventory=json.loads((args.backup/'inventory.json').read_text())
aliases=yaml.safe_load(Path('content/legacy-type-map.yaml').read_text())['aliases']
types=json.loads((source/'extra/types.json').read_text())['types']
assert {t['id'] for t in types}==set(aliases)
staged=[]
for card in inventory['cards']:
    path=source/card['path'];raw=path.read_text();meta=yaml.safe_load(raw.split('---',2)[1])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==card['sha256']
    staged.append({'legacy_id':meta['id'],'legacy_type':meta['type'],'candidate_skill_ids':aliases[meta['type']],
                   'metadata':meta,'raw_markdown':raw,'sha256':card['sha256'],'publication_status':'review_required'})
events=json.loads((source/'extra/log.json').read_text())['events']
payload={'schema_version':1,'cards':staged,'events':events,'types':types,
         'config':json.loads((source/'extra/config.json').read_text()),'current':json.loads((source/'extra/current.json').read_text()),
         'warnings':['Date-only legacy entries retain unknown time and timezone.',
                     'Do not infer elapsed time for paused current attempt from started timestamp.',
                     'One legacy type may map to multiple skills; choose primary and per-part skills on review.',
                     'Control PDFs were not parsed and are excluded from staged learning content.',
                     'Legacy widgets and DataviewJS are preserved as source, never executed by the application.']}
target=args.backup/'migration-dry-run.json';target.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str))
assert len(staged)==inventory['counts']['cards'] and len({p['legacy_id'] for p in staged})==len(staged)
minutes=sum(e.get('minutes',0) for e in events)
assert minutes==inventory['counts']['minutes']
print(f'Staged {len(staged)} unique cards, {len(types)} types, {len(events)} events, {minutes} minutes; canonical source text and IDs preserved. Nothing imported or published.')
