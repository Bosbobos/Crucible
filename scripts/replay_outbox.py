import argparse
from ops import compose

parser=argparse.ArgumentParser();parser.add_argument('--service',required=True,choices=['content','practice','learning','reports']);args=parser.parse_args()
code="""import json;from pathlib import Path;from platformkit.runtime import db
cfg=json.loads(Path('/run/secrets/config').read_text())
with db(cfg) as conn:
 result=conn.execute('UPDATE outbox SET published_at=NULL')
 print('Scheduled replay of',result.rowcount,'retained own outbox events')
"""
print(compose('exec','-T',args.service,'python','-c',code).stdout.strip())
