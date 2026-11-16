"""Запуск только на disposable PostgreSQL: CRUCIBLE_CHARACTER_TEST_DSN, БД *_test."""
import copy
import importlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from platformkit.runtime import db
from character_service.store import apply_event,ensure_profile
from test_progression import fact


@pytest.fixture
def cfg(tmp_path,monkeypatch):
    dsn=os.getenv('CRUCIBLE_CHARACTER_TEST_DSN')
    if not dsn:pytest.skip('Нужна отдельная disposable БД *_test')
    with psycopg.connect(dsn) as conn:
        assert conn.execute('SELECT current_database()').fetchone()[0].endswith('_test')
        conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
        for path in sorted(Path('migrations/character').glob('[0-9]*.sql')):conn.execute(path.read_text())
    key=Ed25519PrivateKey.generate()
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    config={'dsn':dsn,'service':'character-service','public_key':public,'amqp_url':'amqp://invalid','queue':'character.in'}
    path=tmp_path/'config.json';path.write_text(json.dumps(config));monkeypatch.setenv('CRUCIBLE_CONFIG',str(path))
    def headers(scopes=None,profile='owner',subject='test-owner'):
        token=jwt.encode({'iss':'crucible','sub':subject,'profile_id':profile,'aud':'character-service',
            'scopes':scopes if scopes is not None else ['character:read','character:write','diagnostics:read'],
            'jti':str(uuid.uuid4()),'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},private,algorithm='EdDSA')
        return {'Authorization':'Bearer '+token}
    return config,headers


def event(f=None,revision=1):
    f=f or fact()
    return {'schema_version':1,'event_id':str(uuid.uuid4()),'event_type':'practice.learning-facts.changed.v1',
        'producer':'practice-service','profile_id':'owner','source_seq':revision,'aggregate_id':f['snapshot']['attempt_id'],
        'aggregate_revision':revision,'occurred_at':'2026-11-01T10:00:00Z','correlation_id':str(uuid.uuid4()),
        'payload':{'problem_id':f['snapshot']['problem_id'],'content_release_id':'fixture-v1','problem_family_id':'fixture',
            'primary_skill_id':'LA-01','level':'B','attempt_status':'completed','completed_at':'2026-11-01T10:00:00Z',
            'part_outcomes':[{'part_id':'a','skill_id':'LA-01','outcome':'independent'}],
            'mathematical_help_used':False,'active_minutes':1,'eligible_for_progress':True,'active_attempt_id':None,'character_fact':f}}


def total(c):
    with db(c) as conn:
        return conn.execute('SELECT coalesce(sum(delta),0) AS xp FROM xp_ledger').fetchone()['xp']


def test_commit_crashes_duplicates_revisions_and_compensation(cfg):
    c,_=cfg;e=event()
    with pytest.raises(RuntimeError,match='crash before commit'):
        with db(c) as conn:
            apply_event(conn,c,e)
            raise RuntimeError('crash before commit')
    assert total(c)==0
    with db(c) as conn:assert apply_event(conn,c,e)['delta']==80
    # Simulated crash after commit before ACK: repeat with the same event ID.
    with db(c) as conn:assert apply_event(conn,c,e)['status']=='duplicate'
    again=copy.deepcopy(e);again['event_id']=str(uuid.uuid4())
    with db(c) as conn:assert apply_event(conn,c,again)['status']=='semantic_duplicate'
    changed=event(fact(outcome='assisted'),3)
    with db(c) as conn:assert apply_event(conn,c,changed)['delta']==-24
    with db(c) as conn:assert apply_event(conn,c,event(revision=2))['status']=='stale'
    assert total(c)==56
    revoked=copy.deepcopy(changed);revoked['event_id']=str(uuid.uuid4());revoked['aggregate_revision']=4;revoked['payload']['character_fact']['status']='revoked'
    revoked['payload']['character_fact']['reason']='Synthetic revocation test'
    with db(c) as conn:assert apply_event(conn,c,revoked)['delta']==-56
    assert total(c)==0


def test_id_and_revision_conflicts_rollback_and_other_events_continue(cfg):
    c,_=cfg;e=event()
    with db(c) as conn:apply_event(conn,c,e)
    conflict=copy.deepcopy(e);conflict['payload']['character_fact']['snapshot']['parts'][0]['quality']=.5
    with pytest.raises(ValueError):
        with db(c) as conn:apply_event(conn,c,conflict)
    conflict['event_id']=str(uuid.uuid4())
    with pytest.raises(ValueError):
        with db(c) as conn:apply_event(conn,c,conflict)
    with db(c) as conn:assert apply_event(conn,c,event(fact('b',equivalence='other')))['delta']==80
    assert total(c)==160


def client(cfg):
    import character_service.main as main
    importlib.reload(main)
    return TestClient(main.app)


def test_loadout_ownership_revision_receipts_and_no_auto_equip(cfg):
    c,headers=cfg;api=client(cfg);h=headers()
    original=api.get('/api/character/v1/me/loadout',headers=h).json()
    slots={**original['slots'],'sword':'sword-0'}
    command={'command_id':str(uuid.uuid4()),'expected_revision':original['revision'],'slots':slots}
    first=api.put('/api/character/v1/me/loadout',headers=h,json=command)
    assert first.status_code==200,first.text
    assert api.put('/api/character/v1/me/loadout',headers=h,json=command).json()==first.json()
    changed={**command,'slots':{**slots,'chest':None}}
    assert api.put('/api/character/v1/me/loadout',headers=h,json=changed).status_code==409
    changed['command_id']=str(uuid.uuid4())
    assert api.put('/api/character/v1/me/loadout',headers=h,json=changed).status_code==409
    for bad in ('sword-4','unknown','armor-0-chest'):
        body={'command_id':str(uuid.uuid4()),'expected_revision':2,'slots':{**slots,'sword':bad}}
        assert api.put('/api/character/v1/me/loadout',headers=h,json=body).status_code==422
    # Fresh C grants sigil, leaves every saved slot unchanged.
    with db(c) as conn:apply_event(conn,c,event(fact(difficulty='C')))
    assert api.get('/api/character/v1/me/loadout',headers=h).json()['slots']==slots
    with db(c) as conn:apply_event(conn,c,event(fact(difficulty='C',outcome='assisted'),2))
    inventory=api.get('/api/character/v1/me/inventory',headers=h).json()['items']
    sigil=next(i for i in inventory if i['id']=='sigil-LA')
    assert sigil['owned'] and sigil['evidence_recheck'] and not sigil['equipped']


def test_two_tabs_atomic_conflict_security_and_collection(cfg):
    c,headers=cfg;api=client(cfg);h=headers()
    loadout=api.get('/api/character/v1/me/loadout',headers=h).json()
    def put(slot):
        return api.put('/api/character/v1/me/loadout',headers=h,json={'command_id':str(uuid.uuid4()),
            'expected_revision':1,'slots':{**loadout['slots'],slot:None}}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(put,['chest','legs']))==[200,409]
    assert api.get('/api/character/v1/me/summary').status_code==401
    assert api.get('/api/character/v1/me/inventory',headers=headers(profile='another-user')).status_code==403
    assert api.put('/api/character/v1/me/loadout',headers=headers(scopes=['character:read']),json={
        'command_id':str(uuid.uuid4()),'expected_revision':2,'slots':loadout['slots']}).status_code==403
    assert api.post('/api/character/v1/grant-xp',headers=h,json={'xp':100}).status_code==404
    assert api.get('/api/character/v1/me/collection',headers=h).json()['positions']==[None]*9
    invalid={'command_id':str(uuid.uuid4()),'expected_revision':1,'positions':['relic-01']+[None]*8}
    assert api.put('/api/character/v1/me/collection',headers=h,json=invalid).status_code==422


def test_migration_rollback_roundtrip(cfg):
    c,_=cfg
    with db(c) as conn:
        ensure_profile(conn)
        conn.execute(Path('migrations/character/rollback.sql').read_text())
        for path in sorted(Path('migrations/character').glob('[0-9]*.sql')):conn.execute(path.read_text())
        ensure_profile(conn)
        assert conn.execute('SELECT count(*) AS count FROM item_ownership').fetchone()['count']==7


def test_contiguous_main_cursor_and_independent_profile_stream(cfg):
    c,_=cfg
    with db(c) as conn:
        apply_event(conn,c,event(revision=3))
        assert conn.execute("SELECT applied_seq FROM source_checkpoints WHERE source='practice-service'").fetchone()['applied_seq']==0
        apply_event(conn,c,event(revision=2))
        profile=event(revision=1);profile.update(event_type='learning.character-profile.changed.v1',producer='learning-service',
            source_stream='character-profile',aggregate_id='owner',payload={'timezone':'America/New_York','revision':1})
        apply_event(conn,c,profile)
        assert conn.execute("SELECT timezone FROM profile_settings_projection").fetchone()['timezone']=='America/New_York'
        assert conn.execute("SELECT applied_seq FROM source_checkpoints WHERE source='practice-service'").fetchone()['applied_seq']==0
        apply_event(conn,c,event(revision=1))
        assert conn.execute("SELECT applied_seq FROM source_checkpoints WHERE source='practice-service'").fetchone()['applied_seq']==3
        assert total(c)==0 # uncommitted transaction is invisible through a separate connection
    assert total(c)==80


def test_collection_duplicate_rejected_and_rearrangement_atomic(cfg):
    c,headers=cfg;api=client(cfg);h=headers()
    api.get('/api/character/v1/me/collection',headers=h)
    # Только ownership fixture в disposable DB; начисление XP здесь не тестируется.
    with db(c) as conn:
        for relic in ('relic-01','relic-02'):
            conn.execute("INSERT INTO item_ownership(profile_id,item_id,current_qualified) VALUES ('owner',%s,true)",(relic,))
    positions=['relic-01','relic-02']+[None]*7
    first=api.put('/api/character/v1/me/collection',headers=h,json=dict(command_id=str(uuid.uuid4()),expected_revision=1,positions=positions))
    assert first.status_code==200
    bad=api.put('/api/character/v1/me/collection',headers=h,json=dict(command_id=str(uuid.uuid4()),expected_revision=2,positions=['relic-01','relic-01']+[None]*7))
    assert bad.status_code==422
    assert api.get('/api/character/v1/me/collection',headers=h).json()['positions']==positions
    swapped=['relic-02','relic-01']+[None]*7
    assert api.put('/api/character/v1/me/collection',headers=h,json=dict(command_id=str(uuid.uuid4()),expected_revision=2,positions=swapped)).json()['positions']==swapped
    path=api.get('/api/character/v1/me/path',headers=h).json()
    assert len(path['trials'])==8 and all('profiles' not in trial for trial in path['trials'])
