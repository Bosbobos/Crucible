import json
import time
import os
from pathlib import Path
from datetime import datetime,timezone
from ops import ASSESSMENT,SECRETS,compose,evidence,run,container,refresh_firewall

if os.getenv('CRUCIBLE_DEMO')!='1':raise SystemExit('Set CRUCIBLE_DEMO=1 on the synthetic stack')

brokers=['rabbitmq']+(['rabbitmq2','rabbitmq3'] if ASSESSMENT else [])
learning_id=container('learning')
existing=set(json.loads(run(['docker','inspect',learning_id]).stdout)[0]['NetworkSettings']['Networks'])
attached=[]
try:
    run([str(Path.cwd()/'scripts/firewall'),'rollback'])
    compose('stop','-t','20','web','reports',*brokers)
    # Network calls are bounded at 4s; SQL statements at 8s. Drain requests accepted
    # before the gateway stopped before taking the source snapshots.
    time.sleep(12)
    for service,suffix in [('practice','_practice_api'),('content','_content_api')]:
        networks=json.loads(run(['docker','inspect',container(service)]).stdout)[0]['NetworkSettings']['Networks']
        network=next(n for n in networks if n.endswith(suffix))
        if network not in existing:
            run(['docker','network','connect',network,learning_id]);attached.append(network)
    result=compose('exec','-T','learning','python','-m','service.rebuild').stdout.strip()
    evidence('projection-rebuild',{'at':datetime.now(timezone.utc),'assessment':ASSESSMENT,'result':result})
    print(result)
finally:
    for network in attached:run(['docker','network','disconnect',network,learning_id],check=False)
    compose('start',*brokers,'reports','web')
    refresh_firewall()
