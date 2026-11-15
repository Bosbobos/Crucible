import argparse
import json
import os
from pathlib import Path
from uuid import UUID
import httpx
from pydantic import BaseModel, ConfigDict, Field


class ReviewImport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    command_id:UUID
    attempt_id:UUID
    expected_revision:int=Field(ge=1)
    text:str=Field(min_length=1,max_length=16000)


parser=argparse.ArgumentParser();parser.add_argument('file',type=Path);args=parser.parse_args()
if args.file.stat().st_size>64000:raise SystemExit('Review import exceeds 64 KB')
body=ReviewImport.model_validate_json(args.file.read_text())
cfg=json.loads(Path('.secrets/mcp.json').read_text())
if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1':
    from ops import api_base_url
    cfg['base_url']=api_base_url()
payload=body.model_dump(mode='json');attempt=payload.pop('attempt_id')
r=httpx.post(cfg['base_url']+'/api/v1/practice/attempts/'+attempt+'/reviews',json=payload,
             headers={'Authorization':'Bearer '+cfg['tokens']['practice']},timeout=8)
r.raise_for_status();print(r.json())
