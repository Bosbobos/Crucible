"""Одна транзакция: inbox → snapshot → права → ledger → summary → outbox."""
import hashlib
import json
import time
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from psycopg.types.json import Jsonb
from contracts.events import Event, PracticeFact
from contracts.campaign import Campaign
from platformkit.runtime import canonical, db, emit, iso,log
from .definitions import DATA, HASH, CATALOG_VERSION, RULESET, STARTING, SLOTS
from .domain import recompute, parts, instant

SCHEMAS = {'attempt_result':'attempt-snapshot', 'learning_unit_completed':'learning-unit-snapshot',
           'diagnostic_result':'diagnostic-snapshot','assessment_result':'assessment-snapshot'}
VALIDATORS = {k:Draft202012Validator(json.loads((Path(__file__).with_name('contracts')/(v+'.schema.json')).read_text()),
                                   format_checker=FormatChecker()) for k,v in SCHEMAS.items()}


def validate_fact(fact):
    if not {'fact_type','status','snapshot'}<=set(fact) or set(fact)-{'fact_type','status','snapshot','reason'} or fact['fact_type'] not in VALIDATORS or fact['status'] not in {'confirmed','revoked'}:
        raise ValueError('Неизвестный формат факта')
    if 'reason' in fact and (not isinstance(fact['reason'],str) or len(fact['reason'])>2000):
        raise ValueError('Некорректная причина исправления')
    if fact['status']=='revoked' and not fact.get('reason','').strip():
        raise ValueError('Аннулирование требует причины')
    # Reject NaN/Infinity even if the JSON decoder permits them.
    json.dumps(fact, allow_nan=False)
    errors = list(VALIDATORS[fact['fact_type']].iter_errors(fact['snapshot']))
    if errors:
        raise ValueError('Snapshot не соответствует закрытому контракту')
    s = fact['snapshot']
    instant(s['completed_at'])
    if fact['fact_type']=='attempt_result':
        parts(s['parts'])
        if instant(s['began_at'])>instant(s['completed_at']):
            raise ValueError('Некорректная хронология')
        if s['help_during_attempt'] is True and all(p['outcome']=='independent' for p in s['parts']):
            raise ValueError('Помощь несовместима с независимым итогом')
    if 'correct_count' in s and s['correct_count'] is not None and s['total_count'] is not None and s['correct_count']>s['total_count']:
        raise ValueError('Score больше total')
    return fact


def ensure_profile(conn, profile='owner'):
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('character:'+profile,))
    row = conn.execute('SELECT * FROM definition_publications WHERE version=%s', (CATALOG_VERSION,)).fetchone()
    if row and row['sha256']!=HASH:
        raise ValueError('Опубликованная версия definitions изменена')
    conn.execute('INSERT INTO definition_publications(version,sha256,definitions) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                 (CATALOG_VERSION,HASH,Jsonb(DATA)))
    initial = recompute([],campaign_bindings(conn))
    conn.execute('INSERT INTO character_profile(profile_id,summary) VALUES (%s,%s) ON CONFLICT DO NOTHING',(profile,Jsonb(initial)))
    for item in STARTING:
        conn.execute('INSERT INTO item_ownership(profile_id,item_id,current_qualified) VALUES (%s,%s,true) ON CONFLICT DO NOTHING',(profile,item))
    # Initial outfit is an explicit creation default; later grants never change it.
    slots = {s:('armor-0-'+s if s in ('chest','shoulders','bracers','legs') else None) for s in SLOTS}
    conn.execute('INSERT INTO loadouts(profile_id,slots) VALUES (%s,%s) ON CONFLICT DO NOTHING',(profile,Jsonb(slots)))
    conn.execute('INSERT INTO collection_placements(profile_id,positions) VALUES (%s,%s) ON CONFLICT DO NOTHING',(profile,Jsonb([None]*9)))
    conn.execute('INSERT INTO preferences(profile_id,preferences) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                 (profile,Jsonb({'rpg_visible':True,'focus_mode':False,'pinned_reward':None})))
    return conn.execute('SELECT * FROM character_profile WHERE profile_id=%s FOR UPDATE',(profile,)).fetchone()


def campaign_bindings(conn):
    row=conn.execute('SELECT bindings FROM campaign_projection WHERE singleton').fetchone()
    return row['bindings'] if row else {}


def apply_event(conn, cfg, raw):
    event = Event.model_validate(raw)
    routes={'practice.learning-facts.changed.v1':('practice-service','main'),
            'practice.character-evidence.changed.v1':('practice-service','character-evidence'),
            'content.character-campaign.published.v1':('content-service','character-campaign'),
            'learning.character-profile.changed.v1':('learning-service','character-profile')}
    if routes.get(event.event_type)!=(event.producer,event.source_stream) or event.profile_id!='owner':
        raise ValueError('Producer не владеет этим фактом')
    campaign=None;settings=None
    if event.event_type=='practice.learning-facts.changed.v1':
        fact=PracticeFact.model_validate(event.payload).character_fact
        if fact is not None and fact['fact_type']!='attempt_result':
            raise ValueError('Неверный тип practice snapshot')
    elif event.event_type=='practice.character-evidence.changed.v1':
        if set(event.payload)!={'fact'}:raise ValueError('Неверный evidence envelope')
        fact=event.payload['fact']
    elif event.event_type=='content.character-campaign.published.v1':
        campaign=Campaign.model_validate(event.payload).model_dump(mode='json');fact=None
    else:
        from zoneinfo import ZoneInfo
        settings=event.payload;fact=None
        if set(settings)!={'timezone','revision'} or settings['revision']!=event.aggregate_revision:
            raise ValueError('Неверная проекция настроек')
        ZoneInfo(settings['timezone'])
    if fact is not None:
        validate_fact(fact)
        id_field={'attempt_result':'attempt_id','learning_unit_completed':'unit_id',
                  'diagnostic_result':'check_id','assessment_result':'assessment_id'}[fact['fact_type']]
        if fact['snapshot'][id_field]!=event.aggregate_id:
            raise ValueError('Неверный fact ID/owner')
    profile = event.profile_id
    row = ensure_profile(conn,profile)
    digest = hashlib.sha256(canonical(raw).encode()).hexdigest()
    source=event.producer if event.source_stream=='main' else event.producer+':'+event.source_stream
    prior = conn.execute('SELECT * FROM inbox_events WHERE producer=%s AND event_id=%s',(source,event.event_id)).fetchone()
    if prior:
        if prior['event_hash']!=digest:
            raise ValueError('Event ID повторно использован с другим payload')
        return {'status':'duplicate','summary_revision':row['revision']}
    conn.execute('INSERT INTO inbox_events(producer,event_id,event_hash,source_seq,correlation_id,disposition) VALUES (%s,%s,%s,%s,%s,%s)',
                 (source,event.event_id,digest,event.source_seq,event.correlation_id,'ignored' if fact is None and campaign is None and settings is None else 'applied'))
    conn.execute('INSERT INTO source_checkpoints VALUES (%s,%s) ON CONFLICT DO NOTHING',
                 (source,cfg.get('initial_practice_seq',0) if source=='practice-service' else 0))
    cursor=conn.execute('SELECT applied_seq FROM source_checkpoints WHERE source=%s FOR UPDATE',(source,)).fetchone()['applied_seq']
    while conn.execute('SELECT 1 FROM inbox_events WHERE producer=%s AND source_seq=%s',(source,cursor+1)).fetchone():cursor+=1
    conn.execute('UPDATE source_checkpoints SET applied_seq=%s WHERE source=%s',(cursor,source))
    if fact is None and campaign is None and settings is None:
        return {'status':'not_applicable','summary_revision':row['revision']}
    if campaign is not None:
        h=hashlib.sha256(canonical(campaign).encode()).hexdigest()
        old=conn.execute('SELECT sha256 FROM campaign_publications WHERE publication_version=%s',(campaign['publication_version'],)).fetchone()
        if old and old['sha256']!=h:raise ValueError('Campaign version/hash conflict')
        conn.execute('INSERT INTO campaign_publications(publication_version,sha256,bindings) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                     (campaign['publication_version'],h,Jsonb(campaign)))
        prior=conn.execute('SELECT source_seq FROM campaign_projection WHERE singleton').fetchone()
        if prior and prior['source_seq']>=event.source_seq:return {'status':'stale','summary_revision':row['revision']}
        conn.execute('''INSERT INTO campaign_projection VALUES (true,%s,%s,%s) ON CONFLICT(singleton)
            DO UPDATE SET source_seq=excluded.source_seq,publication_version=excluded.publication_version,bindings=excluded.bindings''',
            (event.source_seq,campaign['publication_version'],Jsonb(campaign)))
    if settings is not None:
        conn.execute('''INSERT INTO profile_settings_projection VALUES (%s,%s,%s) ON CONFLICT(profile_id)
            DO UPDATE SET revision=excluded.revision,timezone=excluded.timezone WHERE profile_settings_projection.revision<excluded.revision''',
            (profile,event.aggregate_revision,settings['timezone']))
    if fact is not None:
        apply_fact(conn,event,fact,profile,source,row)
        current=conn.execute('SELECT disposition FROM inbox_events WHERE producer=%s AND event_id=%s',(source,event.event_id)).fetchone()['disposition']
        if current in ('stale','semantic_duplicate'):
            result={'status':current,'summary_revision':row['revision'],'delta':0,'items':[]}
            conn.execute('INSERT INTO operations VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(profile,event.correlation_id,Jsonb(result)))
            return result
    facts = [r['fact'] for r in conn.execute('SELECT fact FROM source_facts WHERE profile_id=%s',(profile,)).fetchall()]
    calculated = recompute(facts,campaign_bindings(conn))
    return project(conn,cfg,event,row,calculated)


def apply_fact(conn,event,fact,profile,source,row):
    args = (profile,event.producer,fact['fact_type'],event.aggregate_id)
    previous = conn.execute('SELECT * FROM source_facts WHERE profile_id=%s AND producer=%s AND fact_type=%s AND fact_id=%s',args).fetchone()
    fact_hash = hashlib.sha256(canonical(fact).encode()).hexdigest()
    disposition = None
    if previous:
        if previous['revision']>event.aggregate_revision:
            disposition='stale'
        elif previous['revision']==event.aggregate_revision:
            if previous['fact_hash']!=fact_hash:
                raise ValueError('Та же revision с другим snapshot')
            disposition='semantic_duplicate'
        else:
            old, new = previous['fact']['snapshot'], fact['snapshot']
            immutable={'attempt_result':('attempt_id','problem_id','content_version','reward_equivalence_id','began_at','completed_at'),
                'learning_unit_completed':('unit_id','unit_kind','volume_id','content_version','completed_at'),
                'diagnostic_result':('check_id','check_version','volume_id','completed_at'),
                'assessment_result':('assessment_id','variant_id','publication_version','completed_at')}[fact['fact_type']]
            if any(old[k]!=new[k] for k in immutable):
                raise ValueError('Изменена неизменяемая идентичность попытки')
    if disposition:
        conn.execute('UPDATE inbox_events SET disposition=%s WHERE producer=%s AND event_id=%s',(disposition,source,event.event_id))
        return
    conn.execute('''INSERT INTO source_facts VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(profile_id,producer,fact_type,fact_id) DO UPDATE SET revision=excluded.revision,fact_hash=excluded.fact_hash,fact=excluded.fact''',
                 (*args,event.aggregate_revision,fact_hash,Jsonb(fact)))
    conn.execute('INSERT INTO fact_revisions VALUES (%s,%s,%s,%s,%s,%s,%s)',(*args,event.aggregate_revision,Jsonb(fact),event.event_id))


def project(conn,cfg,event,row,calculated):
    profile=event.profile_id
    revision = row['revision']+1
    applied = {r['business_key']:r['amount'] for r in conn.execute('SELECT * FROM xp_entitlements WHERE profile_id=%s',(profile,)).fetchall()}
    total_delta = 0
    for key in sorted(applied.keys() | calculated['entitlements'].keys()):
        desired = calculated['entitlements'].get(key,0)
        delta = desired-applied.get(key,0)
        evidence = calculated['evidence'].get(key,[])
        if delta:
            conn.execute('''INSERT INTO xp_ledger(profile_id,business_key,delta,summary_revision,event_id,source_revision,correlation_id,ruleset,evidence)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (profile,key,delta,revision,event.event_id,event.aggregate_revision,event.correlation_id,RULESET,Jsonb(evidence)))
            total_delta += delta
        conn.execute('''INSERT INTO xp_entitlements VALUES (%s,%s,%s,%s) ON CONFLICT(profile_id,business_key)
            DO UPDATE SET amount=excluded.amount,evidence=excluded.evidence''',(profile,key,desired,Jsonb(evidence)))
    qualified = set(calculated['qualified_items'])
    owned = {r['item_id'] for r in conn.execute('SELECT item_id FROM item_ownership WHERE profile_id=%s',(profile,)).fetchall()}
    granted = sorted(qualified-owned)
    for item in granted:
        conn.execute('INSERT INTO item_ownership(profile_id,item_id,current_qualified) VALUES (%s,%s,true)',(profile,item))
    for item in owned | qualified:
        conn.execute('UPDATE item_ownership SET current_qualified=%s,evidence_recheck=%s WHERE profile_id=%s AND item_id=%s',
                     (item in qualified,item not in qualified,profile,item))
    for key, state in calculated['seals'].items():
        conn.execute('''INSERT INTO seal_state VALUES (%s,%s,%s,%s) ON CONFLICT(profile_id,seal_id)
            DO UPDATE SET state=excluded.state,ever_granted=seal_state.ever_granted OR excluded.ever_granted''',
            (profile,key,Jsonb(state),state['current_qualified']))
    conn.execute('UPDATE character_profile SET revision=%s,summary=%s,computed_at=now() WHERE profile_id=%s',(revision,Jsonb(calculated),profile))
    result = {'status':'applied','summary_revision':revision,'delta':total_delta,'items':granted}
    conn.execute('''INSERT INTO operations VALUES (%s,%s,%s) ON CONFLICT(profile_id,correlation_id) DO UPDATE SET result=excluded.result''',
                 (profile,event.correlation_id,Jsonb(result)))
    if total_delta or granted:
        conn.execute('INSERT INTO reward_journal(profile_id,correlation_id,summary_revision,delta,items) VALUES (%s,%s,%s,%s,%s)',
                     (profile,event.correlation_id,revision,total_delta,Jsonb(granted)))
    emit(conn,cfg,'character.progress.updated.v1',profile,profile,revision,result,event.correlation_id)
    return result


def consume(cfg, raw):
    started=time.perf_counter()
    with db(cfg) as conn:
        result=apply_event(conn,cfg,raw)
    log.info(canonical({'service':'character-service','operation':'projection.committed','event_id':raw.get('event_id'),
        'correlation_id':raw.get('correlation_id'),'source_revision':raw.get('aggregate_revision'),
        'ruleset':RULESET,'status':result['status'],'delta':result.get('delta',0),
        'processing_ms':round((time.perf_counter()-started)*1000,2)}))
    return result
