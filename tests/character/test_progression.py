import copy
import itertools
from datetime import datetime, timedelta, timezone
import pytest
from character_service.definitions import DATA, STARTING, validate
from character_service.domain import candidate, recompute, level_for, rhythm
from character_service.store import validate_fact


def fact(attempt='a',outcome='independent',quality=1,at='2026-11-01T10:00:00Z',equivalence='eq',**changes):
    s={'attempt_id':attempt,'problem_id':'synthetic-'+attempt,'content_version':'fixture-v1','rubric_version':'rubric-v1',
       'reward_equivalence_id':equivalence,'family_id':'f-'+attempt,'discipline_id':'LA','mapped_volume_id':None,'mapping_version':None,
       'difficulty':'B','parts':[{'part_id':'a','weight':1,'outcome':outcome,'quality':quality,'note_saved':outcome=='reviewed'}],
       'began_at':at,'completed_at':at,'source_sequence':0,'provenance':{'assessment_source':'self_assessment','owner_confirmed':True},
       'freshness':{'statement_seen_before_attempt':False,'solution_seen_before_attempt':False,'worked_example_seen_before_attempt':False},
       'help_during_attempt':outcome=='assisted','review_context':None}
    s.update(changes)
    return {'fact_type':'attempt_result','status':'confirmed','snapshot':s}


def test_definitions_and_all_threshold_boundaries():
    assert len(STARTING)==7
    assert len(DATA['items']['items'])==59
    assert len(DATA['trial_blueprints']['blueprints'])==58
    for row in DATA['progression']['levels']:
        assert level_for(row['total_xp'])==row['level']
        if row['total_xp']:
            assert level_for(row['total_xp']-1)==row['level']-1
    bad=copy.deepcopy(DATA);bad['items']['items'][0]['grants_xp']=80
    with pytest.raises(ValueError):validate(bad)


@pytest.mark.parametrize('outcome,quality,note,expected',[
    ('independent',1,False,80),('assisted',1,False,56),('independent',.9,False,72),
    ('reviewed',0,True,28),('reviewed',0,False,0),('skipped',1,True,0)])
def test_exact_partial_prices(outcome,quality,note,expected):
    s=fact(outcome=outcome,quality=quality)['snapshot'];s['parts'][0]['note_saved']=note
    assert candidate(s)==expected
    if outcome=='reviewed':assert candidate(s,repeat=True)==0


def test_equal_weight_mixed_is_68_and_rounds_once():
    s=fact()['snapshot'];s['parts'].append({'part_id':'b','weight':1,'outcome':'assisted','quality':1,'note_saved':False})
    assert candidate(s)==68
    s['parts'][0]['quality']=.9;s['parts'][1]['quality']=.9
    assert candidate(s)==61
    wrapped={'fact_type':'attempt_result','status':'confirmed','snapshot':s}
    s['help_during_attempt']=True
    validate_fact(wrapped)


def test_primary_max_compensation_and_arrival_order():
    values=[fact('a','reviewed',0),fact('b','assisted'),fact('c')]
    totals=[recompute(values[:i])['xp'] for i in (1,2,3)]
    assert totals==[28,56,80]
    for order in itertools.permutations(values):assert recompute(order)['xp']==80
    corrected=copy.deepcopy(values);corrected[2]['status']='revoked'
    assert recompute(corrected)['xp']-80==-24
    assert recompute([fact('x'),fact('y')])['xp']==80


def repeat_fact(day, **changes):
    at=datetime(2026,11,1,10,tzinfo=timezone.utc)+timedelta(days=day)
    s=fact('r'+str(day),at=at.isoformat(),**changes)
    s['snapshot']['review_context']={'obligation_id':'scheduled-'+str(day),'owner':'learning-service','due_at':at.isoformat(),
        'last_credited_learning_at':(at-timedelta(days=7)).isoformat(),'is_scheduler_obligation':True}
    return s


def test_repeat_timing_due_limit_and_correction():
    values=[fact(),*(repeat_fact(day) for day in (7,14,21,28))]
    assert recompute(values)['xp']==152
    assert recompute(list(reversed(values)))['entitlements']==recompute(values)['entitlements']
    early=repeat_fact(7);early['snapshot']['completed_at']='2026-11-08T09:59:59Z';early['snapshot']['began_at']=early['snapshot']['completed_at']
    assert recompute([fact(),early])['xp']==80
    no_obligation=repeat_fact(7);no_obligation['snapshot']['review_context']=None
    assert recompute([fact(),no_obligation])['xp']==80
    assert recompute([fact(outcome='assisted'),repeat_fact(7,outcome='assisted')])['xp']==72 # 56+floor(16.8)
    assert recompute([fact(outcome='assisted'),repeat_fact(7)])['xp']==80 # primary improvement only
    assert recompute([fact(),repeat_fact(7,quality=.79)])['xp']==80
    revoked=copy.deepcopy(values);revoked[1]['status']='revoked'
    assert recompute(revoked)['xp']==152 # later valid repeat fills the third entitlement
    a,b=repeat_fact(7),repeat_fact(14)
    b['snapshot']['review_context']['obligation_id']=a['snapshot']['review_context']['obligation_id']
    assert recompute([fact(),a,b])['xp']==104


@pytest.mark.parametrize('field,value',[('weight',0),('weight',-1),('weight',True),('quality',float('nan')),
    ('quality',float('inf')),('quality',1.01),('outcome','correct')])
def test_invalid_parts_rejected(field,value):
    s=fact();s['snapshot']['parts'][0][field]=value
    with pytest.raises(ValueError):validate_fact(s)


def test_duplicate_parts_unknown_difficulty_and_assistance_rejected():
    s=fact();s['snapshot']['parts']*=2
    with pytest.raises(ValueError):validate_fact(s)
    s=fact(difficulty='B+')
    with pytest.raises(ValueError):validate_fact(s)
    s=fact(help_during_attempt=True)
    with pytest.raises(ValueError):validate_fact(s)


def test_missing_mapping_never_grants_seals_but_first_c_is_independent():
    s=recompute([fact('a',difficulty='C')])
    assert all(v['status']=='BLOCKED_CONTENT' for v in s['seals'].values())
    assert s['metrics']['first_fresh_independent_C_ge_80:LA']==1
    assert 'sigil-LA' in s['qualified_items']
    unknown=fact(difficulty='C');unknown['snapshot']['freshness']['statement_seen_before_attempt']=None
    assert 'sigil-LA' not in recompute([unknown])['qualified_items']


def test_e_r_require_verified_different_families_and_168h():
    values=[fact('a'),fact('b'),repeat_fact(7,equivalence='third')]
    b={'volumes':{'LA-01':{'binding_status':'bound'}},'problems':{}}
    for f in values:
        s=f['snapshot'];s.update(mapped_volume_id='LA-01',mapping_version='map1')
        b['problems'][s['problem_id']]={k:s[k] for k in ('family_id','rubric_version','content_version','reward_equivalence_id','mapping_version')}
        b['problems'][s['problem_id']]['volume_id']='LA-01'
    s=recompute(values,b)
    assert s['seals']['E-LA-01']['current_qualified']
    assert s['seals']['R-LA-01']['current_qualified']
    b['problems'][values[2]['snapshot']['problem_id']]['family_id']='unverified'
    assert not recompute(values,b)['seals']['R-LA-01']['current_qualified']


def test_cap_chronicle_and_source_rhythm_dst():
    assert level_for(33276+4000)==60
    instants=['2026-11-01T23:30:00Z','2026-11-02T01:30:00Z']
    assert rhythm(instants,'2026-11-02T12:00:00Z','Europe/Moscow')['days_per_7']==1
    assert rhythm(instants,'2026-11-02T12:00:00Z','America/New_York')['days_per_7']==1
    assert rhythm(['2020-01-01T00:00:00Z'],'2026-11-02T12:00:00Z','Europe/Moscow')['days_per_7']==0


def unit(uid,kind,**changes):
    s={'unit_id':uid,'unit_kind':kind,'volume_id':'LA-01','content_version':'fixture-v1',
       'completed_at':'2026-11-01T10:00:00Z','explicit_completion':True,'answers_saved':True,
       'prediction_saved':True,'run_saved':True,'explanation_saved':True,'correct_count':3,'total_count':4,'owner_confirmed':True}
    s.update(changes)
    return {'fact_type':'learning_unit_completed','status':'confirmed','snapshot':s}


def reader_binding(values):
    return {'volumes':{'LA-01':{'theory_section_ids':['s1','s2','s3','s4'],'core_id':'core','lab_id':'lab','final_check_id':'final',
            'diagnostic_id':'diagnostic','diagnostic_version':'d1'}},
        'units':{f['snapshot']['unit_id']:{'volume_id':'LA-01','content_version':'fixture-v1','unit_kind':f['snapshot']['unit_kind']} for f in values}}


def test_reader_84_plus_v40_saved_answers_not_scrolling_or_explanation_length():
    values=[*(unit('s'+str(i),'theory_section',explanation_saved=False) for i in range(1,5)),
        unit('core','core',explanation_saved=False),unit('lab','lab'),unit('final','volume_final_check')]
    b=reader_binding(values)
    s=recompute(values,b)
    assert s['xp']==124 and s['metrics']['seals.V']==1
    missed=copy.deepcopy(values);missed[0]['snapshot']['answers_saved']=False
    assert recompute(missed,b)['xp']==72 # no section12 and V40
    missed=copy.deepcopy(values);missed[-2]['snapshot']['prediction_saved']=False
    assert recompute(missed,b)['xp']==68 # no lab16 and V40
    missed=copy.deepcopy(values);missed[-1]['snapshot']['correct_count']=2
    assert recompute(missed,b)['xp']==72


def test_known_route_does_not_pay_unread_sections_and_corrects_v():
    final=unit('final','volume_final_check');b=reader_binding([final]);b['problems']={}
    attempts=[fact('cold1',equivalence='cold1'),fact('cold2',equivalence='cold2')]
    for f in attempts:
        s=f['snapshot'];s.update(mapped_volume_id='LA-01',mapping_version='m1')
        b['problems'][s['problem_id']]={k:s[k] for k in ('family_id','rubric_version','content_version','reward_equivalence_id','mapping_version')}
        b['problems'][s['problem_id']]['volume_id']='LA-01'
    diagnostic={'fact_type':'diagnostic_result','status':'confirmed','snapshot':{'volume_id':'LA-01','check_id':'diagnostic',
        'check_version':'d1','correct_count':3,'total_count':4,'completed_at':'2026-11-01T10:00:00Z','owner_confirmed':True}}
    values=[final,diagnostic,*attempts]
    s=recompute(values,b)
    assert s['xp']==292 and s['metrics']['seals.E']==s['metrics']['seals.V']==1
    assert all(not k.startswith('unit:s') for k in s['entitlements'])
    values[1]['status']='revoked'
    assert recompute(values,b)['xp']==252


def test_m_requires_registered_weights_diverse_disciplines_and_disjoint_families():
    values=[];b={'assessments':{},'training_family_ids':[]}
    for variant in (1,2,3):
        attempts=[fact(f'm{variant}-{i}',equivalence=f'm{variant}-{i}',discipline_id=d,difficulty='C' if i==5 else 'B')
                  for i,d in enumerate(['LA','CA','PR','DS','OD','LA'])]
        for f in attempts:values.append(f)
        rows=[{'attempt_id':f['snapshot']['attempt_id'],'problem_id':f['snapshot']['problem_id'],
               'weight':15 if i<5 else 25,'score_fraction':1,'is_C':i==5,'independent':True,'fresh_at_start':True} for i,f in enumerate(attempts)]
        bid=f'M-{variant:02d}'
        b['assessments'][bid]={'variant_id':bid,'publication_version':'m1','problem_ids':[r['problem_id'] for r in rows]}
        values.append({'fact_type':'assessment_result','status':'confirmed','snapshot':{'assessment_id':bid,
            'assessment_kind':'M','variant_id':bid,'publication_version':'m1','problem_results':rows,
            'completed_at':'2026-11-01T12:00:00Z','elapsed_seconds':15000,'owner_confirmed':True}})
    s=recompute(values,b)
    assert s['metrics']['seals.M']==3
    assert s['entitlements']['seal:M-01']==200 # timing recorded, not an unlock limit
    values[6]['snapshot']['problem_results'][5]['score_fraction']=.49
    assert recompute(values,b)['metrics']['seals.M']==2
    values[6]['snapshot']['problem_results'][5]['score_fraction']=1
    values[7]['snapshot']['family_id']=values[0]['snapshot']['family_id']
    assert recompute(values,b)['metrics']['seals.M']==2


def test_k_requires_five_e_three_r_registered_weights_and_c_half():
    values=[];b={'volumes':{},'units':{},'problems':{},'assessments':{}}
    for volume in range(1,6):
        vid=f'LA-{volume:02d}';b['volumes'][vid]={'theory_section_ids':[],'core_id':None}
        for index in range(3 if volume<=3 else 2):
            f=fact(f'v{volume}-{index}',equivalence=f'v{volume}-{index}',mapped_volume_id=vid,mapping_version='m1',
                   at='2026-11-08T10:00:00Z' if index==2 else '2026-11-01T10:00:00Z')
            s=f['snapshot'];values.append(f)
            b['problems'][s['problem_id']]={k:s[k] for k in ('family_id','rubric_version','content_version','reward_equivalence_id','mapping_version')}
            b['problems'][s['problem_id']]['volume_id']=vid
    trials=[fact(f'k-{i}',equivalence=f'k-{i}',difficulty='C' if i==3 else 'B') for i in range(4)]
    values+=trials
    rows=[dict(attempt_id=f['snapshot']['attempt_id'],problem_id=f['snapshot']['problem_id'],weight=w,
               score_fraction=1,is_C=i==3,independent=True,fresh_at_start=True) for i,(f,w) in enumerate(zip(trials,[20,25,25,30]))]
    b['assessments']['K-LA']=dict(variant_id='K-LA-v1',publication_version='p1',problem_ids=[r['problem_id'] for r in rows])
    values.append(dict(fact_type='assessment_result',status='confirmed',snapshot=dict(assessment_id='k-result',assessment_kind='K',
        variant_id='K-LA-v1',publication_version='p1',problem_results=rows,completed_at='2026-11-09T10:00:00Z',elapsed_seconds=15000,owner_confirmed=True)))
    assert recompute(values,b)['metrics']['seals.K']==1
    # A source correction makes both the prerequisite and K no longer qualified.
    corrected=copy.deepcopy(values);corrected[2]['status']='revoked'
    assert recompute(corrected,b)['metrics']['seals.K']==0
    corrected=copy.deepcopy(values);corrected[-1]['snapshot']['problem_results'][0]['weight']=19
    assert recompute(corrected,b)['metrics']['seals.K']==0
    corrected=copy.deepcopy(values);corrected[-2]['snapshot']['parts'][0]['quality']=.5;corrected[-1]['snapshot']['problem_results'][-1]['score_fraction']=.5
    assert recompute(corrected,b)['metrics']['seals.K']==1
    corrected[-2]['snapshot']['parts'][0]['quality']=.49;corrected[-1]['snapshot']['problem_results'][-1]['score_fraction']=.49
    assert recompute(corrected,b)['metrics']['seals.K']==0
