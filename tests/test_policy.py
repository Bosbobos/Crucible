from datetime import datetime, timezone, timedelta
from learning_service.policy import calculate, make_plan

AT=datetime(2026,11,13,12,tzinfo=timezone.utc)
CAT=[{'id':f'p{i}','primary_skill_id':'s','problem_family_id':f'f{i}','level':'A' if i==0 else 'B','pool':'train','section':'math'} for i in range(4)]


def fact(i,day,score='independent',family=None):
    return {'attempt_id':str(i),'problem_id':f'p{i}','problem_family_id':family or f'f{i}','primary_skill_id':'s','level':'B',
            'eligible_for_progress':True,'attempt_status':'completed','completed_at':day.isoformat(),
            'part_outcomes':[{'skill_id':'s','outcome':score}], 'mathematical_help_used':False,'active_minutes':3}


def test_transfer_requires_families_days_and_level():
    same=[fact(0,AT),fact(1,AT,family='f0')]
    assert not calculate(same,CAT,AT)[0]['transfer_confirmed']
    assert not calculate([fact(0,AT),fact(1,AT)],CAT,AT)[0]['transfer_confirmed']
    assert calculate([fact(0,AT-timedelta(days=1)),fact(1,AT)],CAT,AT)[0]['transfer_confirmed']


def test_recompute_old_correction_and_due_intervals():
    history=[fact(0,AT-timedelta(days=4)),fact(1,AT)]
    assert calculate(history,CAT,AT)[0]['due_date']=='2026-11-23'
    history[0]['part_outcomes'][0]['outcome']='assisted'
    state=calculate(list(reversed(history)),CAT,AT)[0]
    assert state['due_date']=='2026-11-17'
    assert state['weakness']==.25


def test_help_caps_independence_and_timezone():
    f=fact(0,datetime(2026,11,12,22,tzinfo=timezone.utc))
    f['mathematical_help_used']=True
    assert calculate([f],CAT,AT,'Europe/Moscow')[0]['due_date']=='2026-11-16'
    assert calculate([f],CAT,AT,'UTC')[0]['due_date']=='2026-11-15'


def test_plan_is_deterministic_excludes_holdout_and_uses_fresh_variant():
    facts=[fact(0,AT-timedelta(days=10),'assisted')]
    catalog=CAT+[dict(CAT[0],id='hidden',pool='holdout')]
    skills=calculate(facts,catalog,AT)
    first=make_plan(facts,catalog,skills,AT,3,seed='seed')
    assert first==make_plan(facts,list(reversed(catalog)),skills,AT,3,seed='seed')
    assert len(first['items'])==3
    assert first['items'][0]['id']!='p0'
    assert all(p['id']!='hidden' for p in first['items'])
