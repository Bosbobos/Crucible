import json
from pathlib import Path
from ops import compose
from contracts.content import ContentBundle
from contracts.events import Event, PracticeFact

target=Path('packages/contracts/schemas');target.mkdir(exist_ok=True)
for model in [ContentBundle,Event,PracticeFact]:
    (target/(model.__name__+'.schema.json')).write_text(json.dumps(model.model_json_schema(),ensure_ascii=False,indent=2)+'\n')
for service in ['content','practice','learning','reports']:
    code="import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json').read().decode())"
    data=json.loads(compose('exec','-T',service,'python','-c',code).stdout)
    (target/(service+'.openapi.json')).write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print('Exported current OpenAPI and closed JSON Schemas.')
