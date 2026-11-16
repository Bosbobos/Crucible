import json
import os
import sys
from pathlib import Path
import httpx

cfg=json.loads(Path(os.getenv('CRUCIBLE_OPERATOR_CONFIG','.secrets/operator.json')).read_text())
base_url=os.getenv('CRUCIBLE_BASE_URL',cfg['base_url'])
results={}
for name,path in {'content':'/catalog','practice':'/current','learning':'/progress'}.items():
    try:
        r=httpx.get(base_url+'/api/v1/'+name+path,headers={'Authorization':'Bearer '+cfg['tokens'][name]},timeout=5)
        results[name]={'status':r.status_code}
        if name=='learning' and r.status_code==200:
            data=r.json();results[name].update(applied_practice_seq=data['applied_practice_seq'],catalog_seq=data['catalog_seq'],cache=data['cache'])
    except httpx.HTTPError:results[name]={'status':'unreachable'}
results['backup']={'local_backup_present':any(Path('.private/backups').glob('*.cruciblebackup')),'off_device_copy_configured':False,
                  'automatic_schedule_configured':False}
try:
    r=httpx.get(base_url+'/api/character/v1/me/summary',headers={'Authorization':'Bearer '+cfg['tokens']['character']},timeout=5)
    results['character']={'status':r.status_code}
except (httpx.HTTPError,KeyError):
    results['character']={'status':'unreachable'}
print(json.dumps(results,ensure_ascii=False,indent=2))
if '--require-ready' in sys.argv and any(results[name]['status']!=200 for name in ['content','practice','learning']):
    raise SystemExit(1)
