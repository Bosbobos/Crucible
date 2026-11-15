import json
import os
import time
import uuid
from pathlib import Path
import httpx
import pytest

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('CRUCIBLE_INTEGRATION')!='1',reason='Set CRUCIBLE_INTEGRATION=1 on the synthetic stack')]


def cmd(**kwargs):
    return {'command_id':str(uuid.uuid4()),**kwargs}


def client(kind='test-owner'):
    cfg=json.loads((Path(os.getenv('CRUCIBLE_TEST_CONFIG_DIR','.secrets'))/(kind+'.json')).read_text())
    if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1':
        from ops import api_base_url
        cfg['base_url']=api_base_url()
    else:
        cfg['base_url']=os.getenv('CRUCIBLE_TEST_BASE_URL',cfg['base_url'])
    os.environ['CRUCIBLE_MCP_BASE_URL']=cfg['base_url']
    class Client:
        def request(self,method,path,body=None):
            service=path.split('/')[0]
            return httpx.request(method,cfg['base_url']+'/api/v1/'+path,json=body,
                                 headers={'Authorization':'Bearer '+cfg['tokens'][service]},timeout=12)
        def get(self,path):
            r=self.request('GET',path);assert r.status_code==200,r.text;return r.json()
        def post(self,path,body):
            r=self.request('POST',path,body);assert r.status_code==200,r.text;return r.json()
    return Client()


def wait_progress(c,seq,timeout=25):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        response=c.request('GET','learning/progress?at_least_practice_seq='+str(seq))
        if response.status_code==200:
            p=response.json()
            if not p['pending']:return p
        time.sleep(.2)
    pytest.fail('Projection did not reach '+str(seq))


def clear_active(c):
    current=c.get('practice/current')['attempt']
    if current:
        assert c.request('PATCH','practice/attempts/'+current['id'],cmd(expected_revision=current['revision'],state='abandoned')).status_code==200


def test_complete_learning_review_and_export():
    c=client();agent=client('mcp');clear_active(c)
    catalog=c.get('content/catalog');assert len(catalog['problems'])==57
    p=catalog['problems'][0]
    start=cmd(problem_id=p['id'],content_release_id=catalog['content_release_id'])
    a=c.post('practice/attempts',start);assert c.post('practice/attempts',start)==a
    assert c.request('POST','practice/attempts',cmd(problem_id=p['id'],content_release_id=catalog['content_release_id'])).status_code==409
    base='practice/attempts/'+a['id']
    assert 'solution' not in json.dumps(a['problem'])
    patch=cmd(expected_revision=a['revision'],draft='Synthetic saved solution; <script>not executable</script>')
    a=c.request('PATCH',base,patch).json()
    assert c.request('PATCH',base,patch).json()==a
    assert c.request('PATCH',base,{**patch,'draft':'different'}).status_code==409
    assert c.request('PATCH',base,cmd(expected_revision=1,draft='stale')).status_code==409
    c.post(base+'/questions',cmd(expected_revision=a['revision'],text='Synthetic: why does linearity work without independence?'))
    parts=[{'part_id':p['id'],'outcome':'independent'} for p in a['problem']['parts']]
    complete=cmd(expected_revision=a['revision'],part_outcomes=parts)
    done=c.post(base+'/complete',complete);assert c.post(base+'/complete',complete)==done
    wait_progress(c,done['learning_input_seq'])
    rr=cmd(expected_revision=done['revision'],text='Synthetic review: explain the marginal probabilities.')
    assert agent.post(base+'/reviews',rr)==agent.post(base+'/reviews',rr)
    proposal=agent.post(base+'/proposals',cmd(expected_revision=done['revision'],outcome='assisted',reason='Synthetic correction for the contract test.'))
    assert c.get(base)['part_outcomes'][0]['outcome']=='independent'
    assert agent.request('POST','practice/proposals/'+proposal['proposal_id']+'/approve',cmd()).status_code==403
    corrected=c.post('practice/proposals/'+proposal['proposal_id']+'/approve',cmd())
    assert corrected['part_outcomes'][0]['outcome']=='assisted'
    wait_progress(c,corrected['learning_input_seq'])
    assert c.get(base)['reviews'][0]['stale']
    job=c.post('reports/jobs',cmd())
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        status=c.get('reports/jobs/'+job['job_id'])
        if status['status']=='ready':break
        time.sleep(.25)
    assert status['status']=='ready'
    artifact=c.get('reports/jobs/'+job['job_id']+'/artifact')
    assert artifact['manifest']['source_versions']['practice_seq']>=corrected['learning_input_seq']
    import hashlib
    from platformkit.runtime import canonical
    assert hashlib.sha256(canonical(artifact['artifact']).encode()).hexdigest()==artifact['manifest']['sha256']


def test_help_transaction_and_spoiler_isolation():
    c=client();clear_active(c)
    cat=c.get('content/catalog');p=next(p for p in cat['problems'] if p['id']=='P-005')
    a=c.post('practice/attempts',cmd(problem_id=p['id'],content_release_id=cat['content_release_id']))
    base='practice/attempts/'+a['id']
    problem=c.get('content/problems/P-005?release_id='+cat['content_release_id']+'&include_solution=true')
    assert 'solution' not in problem and 'hints' not in problem
    h=cmd(expected_revision=a['revision'],kind='h1')
    result=c.post(base+'/help',h);assert result==c.post(base+'/help',h)
    assert len(c.get(base)['help'])==1
    revision=result['attempt']['revision']
    parts=[{'part_id':'a','outcome':'independent'}]
    assert c.request('POST',base+'/complete',cmd(expected_revision=revision,part_outcomes=parts)).status_code==422
    c.post(base+'/complete',cmd(expected_revision=revision,part_outcomes=[{'part_id':'a','outcome':'assisted'}]))


def test_browser_auth_csrf_and_logout():
    cfg=json.loads((Path(os.getenv('CRUCIBLE_TEST_CONFIG_DIR','.secrets'))/'operator.json').read_text())
    url=os.getenv('CRUCIBLE_TEST_BASE_URL',cfg['base_url'])
    if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1':
        from ops import api_base_url
        url=api_base_url()
    with httpx.Client(base_url=url,headers={'Origin':cfg['base_url']},timeout=10) as c:
        assert c.get('/api/v1/content/catalog').status_code==401
        response=c.post('/api/v1/practice/auth/login',json={'password':Path(os.getenv('CRUCIBLE_TEST_PASSWORD_FILE','.secrets/owner-password')).read_text()})
        assert response.status_code==200,response.text
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert c.get('/api/v1/content/catalog').status_code==200
        assert c.post('/api/v1/learning/daily-plans',json=cmd()).status_code>=400
        csrf=response.json()['csrf']
        assert c.post('/api/v1/learning/daily-plans',json=cmd(),headers={'X-CSRF-Token':csrf}).status_code==200
        assert c.get('/internal/practice/snapshot').status_code==404
        assert c.post('/api/v1/practice/auth/logout',json={},headers={'X-CSRF-Token':csrf}).status_code==200
        assert c.get('/api/v1/content/catalog').status_code==401
