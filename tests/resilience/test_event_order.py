import json
import os
import subprocess
import time
import pytest
from test_workflow import client,cmd,clear_active,wait_progress

pytestmark=[pytest.mark.resilience,pytest.mark.skipif(os.getenv('CRUCIBLE_RESILIENCE')!='1',reason='Synthetic fault test')]


def dc(*args,input=None):
    return subprocess.run(['docker','compose',*args],input=input,text=True,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout


def test_reordered_and_duplicate_snapshots_do_not_skip_watermark_or_replace_newer_facts():
    c=client();clear_active(c)
    base=c.get('practice/current')['learning_input_seq'];wait_progress(c,base)
    dc('stop','-t','2','rabbitmq')
    try:
        cat=c.get('content/catalog');p=cat['problems'][0]
        a=c.post('practice/attempts',cmd(problem_id=p['id'],content_release_id=cat['content_release_id']))
        a=c.post('practice/attempts/'+a['id']+'/complete',cmd(expected_revision=a['revision'],part_outcomes=[{'part_id':p['id'],'outcome':'independent'} for p in a['problem']['parts']]))
        proposal=c.post('practice/attempts/'+a['id']+'/proposals',cmd(expected_revision=a['revision'],outcome='assisted',reason='Synthetic out-of-order correction'))
        corrected=c.post('practice/proposals/'+proposal['proposal_id']+'/approve',cmd())
        code="""import json,sys;from pathlib import Path;from platformkit.runtime import db
cfg=json.loads(Path('/run/secrets/config').read_text())
with db(cfg) as conn: print(json.dumps([r['event'] for r in conn.execute("SELECT event FROM outbox WHERE (event->>'source_seq')::bigint>%s ORDER BY (event->>'source_seq')::bigint",(int(sys.argv[1]),)).fetchall()]))"""
        events=json.loads(dc('exec','-T','practice','python','-c',code,str(base)))
        assert len(events)==3
        apply="import json,sys;from service.main import consume;consume(json.load(sys.stdin))"
        dc('exec','-T','learning','python','-c',apply,input=json.dumps(events[2]))
        summary=c.get('learning/progress?at_least_practice_seq='+str(corrected['learning_input_seq']))
        assert summary['pending'] and summary['applied_practice_seq']==base
        dc('exec','-T','learning','python','-c',apply,input=json.dumps(events[0]))
        dc('exec','-T','learning','python','-c',apply,input=json.dumps(events[2]))
        assert c.get('learning/progress')['applied_practice_seq']==base+1
        dc('exec','-T','learning','python','-c',apply,input=json.dumps(events[1]))
        done=wait_progress(c,corrected['learning_input_seq'])
        assert done['applied_practice_seq']==base+3
        # An older aggregate revision cannot replace the already applied correction.
        check="""import json,sys;from pathlib import Path;from platformkit.runtime import db
cfg=json.loads(Path('/run/secrets/config').read_text())
with db(cfg) as conn: print(conn.execute('SELECT fact FROM attempt_facts_projection WHERE attempt_id=%s',(sys.argv[1],)).fetchone()['fact']['part_outcomes'][0]['outcome'])"""
        assert dc('exec','-T','learning','python','-c',check,a['id']).strip()=='assisted'
    finally:
        dc('start','rabbitmq')
