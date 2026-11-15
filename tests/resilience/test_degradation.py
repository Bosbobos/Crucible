import os
import time
import subprocess
import pytest
from test_workflow import client,cmd,clear_active,wait_progress

pytestmark=[pytest.mark.resilience,pytest.mark.skipif(os.getenv('CRUCIBLE_RESILIENCE')!='1',reason='Synthetic fault tests require CRUCIBLE_RESILIENCE=1')]


def compose(*args):
    subprocess.run(['docker','compose',*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def test_broker_and_learning_failures_keep_practice_writable():
    c=client();clear_active(c);catalog=c.get('content/catalog');p=catalog['problems'][0]
    a=c.post('practice/attempts',cmd(problem_id=p['id'],content_release_id=catalog['content_release_id']))
    compose('stop','-t','2','rabbitmq','learning')
    try:
        r=c.request('PATCH','practice/attempts/'+a['id'],cmd(expected_revision=a['revision'],draft='Synthetic offline-dependency save'))
        assert r.status_code==200,r.text;a=r.json()
        a=c.post('practice/attempts/'+a['id']+'/complete',cmd(expected_revision=a['revision'],part_outcomes=[{'part_id':p['id'],'outcome':'independent'} for p in a['problem']['parts']]))
        assert c.get('practice/attempts/'+a['id'])['state']=='completed'
    finally:
        compose('start','rabbitmq','learning')
    before=wait_progress(c,a['learning_input_seq'],45)
    replay="import json;from pathlib import Path;from platformkit.runtime import db;c=json.loads(Path('/run/secrets/config').read_text());\nwith db(c) as conn: conn.execute('UPDATE outbox SET published_at=NULL')"
    subprocess.run(['docker','compose','exec','-T','practice','python','-c',replay],check=True)
    time.sleep(1)
    after=c.get('learning/progress')
    assert before['skills']==after['skills'] and before['active_minutes']==after['active_minutes']


def test_redis_fallback_and_content_failure():
    c=client();clear_active(c);cat=c.get('content/catalog');p=cat['problems'][1]
    a=c.post('practice/attempts',cmd(problem_id=p['id'],content_release_id=cat['content_release_id']))
    compose('stop','-t','2','redis','content')
    try:
        progress=c.get('learning/progress');assert progress['cache']=='unavailable'
        r=c.request('PATCH','practice/attempts/'+a['id'],cmd(expected_revision=a['revision'],draft='Synthetic saved without content'))
        assert r.status_code==200;a=r.json()
        assert c.request('POST','practice/attempts/'+a['id']+'/help',cmd(expected_revision=a['revision'],kind='h1')).status_code==503
        assert c.request('POST','practice/attempts/'+a['id']+'/help',cmd(expected_revision=a['revision'],kind='core')).status_code==503
        assert c.get('practice/attempts/'+a['id'])['help']==[]
        a=c.post('practice/attempts/'+a['id']+'/complete',cmd(expected_revision=a['revision'],part_outcomes=[{'part_id':p['id'],'outcome':'independent'} for p in a['problem']['parts']]))
        assert c.request('POST','practice/attempts',cmd(problem_id=p['id'],content_release_id=cat['content_release_id'])).status_code==503
    finally:
        compose('start','redis','content')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if c.request('GET','content/catalog').status_code==200:break
            time.sleep(.2)
        else:raise AssertionError('Content did not become ready after the fault drill')
