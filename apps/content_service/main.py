import hashlib
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError
from contracts.content import ContentBundle
from contracts.campaign import Campaign
from psycopg.types.json import Jsonb
from platformkit.runtime import app_factory, config, db, identity, command, emit, canonical, Command

cfg = config()
app = app_factory(cfg)
PREFIX = '/api/v1/content'


def release(conn, release_id=None):
    row = conn.execute('SELECT * FROM releases WHERE release_id=%s', (release_id,)).fetchone() if release_id else conn.execute('SELECT r.* FROM active_publication a JOIN releases r USING(release_id) WHERE a.singleton').fetchone()
    if not row:
        raise HTTPException(404, 'Опубликованная версия не найдена')
    return row


def metadata(problem):
    return {**{k: problem[k] for k in ['id', 'title', 'primary_skill_id', 'problem_family_id', 'level', 'pool', 'topic_id', 'section', 'estimated_minutes']},
            'skill_title':problem.get('skill_title') or problem['primary_skill_id'], 'family_reviewed':problem.get('family_reviewed',True)}


def availability(topic):
    return {'core':bool(topic.get('core')), 'theory':bool(topic.get('theory')), 'widget':topic.get('widget')}


def visible(problem,topics,binding=None):
    return {**metadata(problem), **{k: problem[k] for k in ['statement', 'parts', 'prerequisites', 'revision', 'provenance']},
            'materials':availability(topics.get(problem['topic_id'],{})),
            # Content-owner policy: legacy cards remain separate stable conditions;
            # family/campaign evidence stays unknown until explicitly curated.
            'reward_metadata': {'reward_equivalence_id':problem.get('reward_equivalence_id') or 'problem:'+problem['id'],
                'family_id':problem['problem_family_id'] if problem.get('family_reviewed') else None,
                'discipline_id':{'linear_algebra':'LA','linalg':'LA','calculus':'CA','multivariable':'CA',
                    'probability':'PR','statistics':'PR','discrete':'DS','combinatorics':'DS','ode':'OD'}.get(problem['section'], problem['primary_skill_id'].split('-')[0]),
                'mapped_volume_id':binding.get('volume_id') if binding else None,
                'mapping_version':binding['mapping_version'] if binding else None,
                'rubric_version':binding['rubric_version'] if binding else 'self-assessment-equal-weights-v1'}}


def validate_bundle(bundle):
    try:
        ContentBundle.model_validate(bundle)
    except ValidationError:
        raise HTTPException(422, 'Материалы не соответствуют версии схемы ContentBundle')
    if set(bundle) != {'schema_version', 'problems', 'topics'} or bundle['schema_version'] != 1:
        raise HTTPException(422, 'Неизвестная схема контента')
    ids, families = set(), set()
    for p in bundle['problems']:
        if p['id'] in ids or p['pool'] not in ['train', 'holdout', 'extension'] or p['level'] not in ['A', 'B', 'C']:
            raise HTTPException(422, 'ID, pool или level некорректен')
        ids.add(p['id'])
        if p['review']['status'] not in ['verified','source_preserved'] or not p['review']['method']:
            raise HTTPException(422, 'Публикация требует проверки')
        if len(p['hints']) != 3 or not all(p['hints']) or not p['solution'] or not p['remember']:
            raise HTTPException(422, 'Неполный материал')
        if (p['topic_id'] is not None and p['topic_id'] not in bundle['topics']) or not p['parts'] or not p['statement']:
            raise HTTPException(422, 'Нарушена ссылочная целостность')
        if p['topic_id'] is not None and p['primary_skill_id'] not in bundle['topics'][p['topic_id']]['skill_ids']:
            raise HTTPException(422, 'Навык отсутствует в связанной теме')
        if len({part['id'] for part in p['parts']}) != len(p['parts']):
            raise HTTPException(422, 'Повтор ID подпункта')
        family_pool = (p['problem_family_id'], p['pool'])
        if any(f == family_pool[0] and pool != family_pool[1] for f, pool in families):
            raise HTTPException(422, 'Семейство пересекает учебные пулы')
        families.add(family_pool)
    for topic in bundle['topics'].values():
        if not (topic.get('core') or topic.get('theory')) or topic.get('widget') not in [None,'expectation','svd','vault-indicators']:
            raise HTTPException(422, 'Неполная тема или неизвестный интерактив')


class Publication(Command):
    bundle: dict


@app.post(PREFIX+'/releases')
def publish(body: Publication, request: Request):
    actor = identity(request, cfg, 'content:publish')
    validate_bundle(body.bundle)
    release_id = 'sha256:'+hashlib.sha256(canonical(body.bundle).encode()).hexdigest()
    with db(cfg) as conn:
        def effect():
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('publication',0))")
            old = conn.execute('SELECT release_id FROM releases WHERE release_id=%s', (release_id,)).fetchone()
            active=conn.execute('SELECT * FROM active_publication WHERE singleton').fetchone()
            if old and active and active['release_id']==release_id:
                return {'release_id': release_id, 'catalog_seq': active['catalog_seq'], 'existing': True}
            if not old:
                conn.execute('INSERT INTO releases(release_id,bundle) VALUES (%s,%s)', (release_id, Jsonb(body.bundle)))
            catalog = [metadata(p) for p in body.bundle['problems'] if p['pool'] == 'train']
            seq = emit(conn, cfg, 'content.catalog.published.v1', 'owner', release_id, 1,
                       {'content_release_id': release_id, 'catalog': catalog}, request.state.request_id)
            conn.execute('''INSERT INTO active_publication(singleton,release_id,catalog_seq) VALUES(true,%s,%s)
                ON CONFLICT(singleton) DO UPDATE SET release_id=excluded.release_id,catalog_seq=excluded.catalog_seq,activated_at=now()''',(release_id,seq))
            return {'release_id': release_id, 'catalog_seq': seq, 'problems': len(catalog)}
        return command(conn, actor, body, 'content.publish', effect)


@app.get(PREFIX+'/catalog')
def catalog(request: Request, release_id: str | None = None):
    identity(request, cfg, 'content:read')
    with db(cfg) as conn:
        r = release(conn, release_id)
        seq=conn.execute("SELECT (event->>'source_seq')::bigint AS seq FROM outbox WHERE event->>'aggregate_id'=%s ORDER BY (event->>'source_seq')::bigint DESC LIMIT 1",(r['release_id'],)).fetchone()
        return {'content_release_id': r['release_id'], 'catalog_seq':seq['seq'] if seq else 0, 'problems': [metadata(p) for p in r['bundle']['problems'] if p['pool'] == 'train'],
                'topics': [{'id': k, 'title': t['title'], 'materials':availability(t), 'provenance':t.get('provenance',{})} for k, t in r['bundle']['topics'].items()]}


@app.get(PREFIX+'/problems/{problem_id}')
def problem(problem_id: str, request: Request, release_id: str):
    identity(request, cfg, 'content:read')
    with db(cfg) as conn:
        r = release(conn, release_id)
        p = next((p for p in r['bundle']['problems'] if p['id'] == problem_id and p['pool'] == 'train'), None)
        if not p:
            raise HTTPException(404, 'Задача недоступна')
        campaign=conn.execute('SELECT bindings FROM active_campaign JOIN campaign_publications USING(publication_version)').fetchone()
        binding=campaign['bindings']['problems'].get(problem_id) if campaign and campaign['bindings']['content_release_id']==r['release_id'] else None
        return {'content_release_id': r['release_id'], **visible(p,r['bundle']['topics'],binding)}


@app.get(PREFIX+'/topics/{topic_id}/{section}')
def topic(topic_id: str, section: Literal['core', 'theory', 'widget'], request: Request, release_id: str):
    identity(request, cfg, 'content:read')
    with db(cfg) as conn:
        r = release(conn, release_id)
        t = r['bundle']['topics'].get(topic_id)
        if not t or t.get(section) is None:
            raise HTTPException(404, 'Тема не найдена')
        return {'id': topic_id, 'title': t['title'], 'content_release_id': release_id, 'section': section, 'text': t[section],
                'widget':t.get('widget'), 'provenance':t.get('provenance',{})}


@app.get('/internal/content/protected/{problem_id}/{kind}')
def protected(problem_id: str, kind: Literal['h1', 'h2', 'h3', 'solution'], request: Request, release_id: str):
    identity(request, cfg, 'content:protected')
    with db(cfg) as conn:
        r = release(conn, release_id)
        p = next((p for p in r['bundle']['problems'] if p['id'] == problem_id and p['pool'] == 'train'), None)
        if not p:
            raise HTTPException(404, 'Задача недоступна')
        return {'kind': kind, 'text': p['solution']+'\n\n'+p['remember'] if kind == 'solution' else p['hints'][int(kind[1])-1]}


class CampaignPublication(Command):
    expected_revision:int=Field(ge=0)
    campaign:Campaign


@app.post(PREFIX+'/campaign-publications')
def publish_campaign(body:CampaignPublication,request:Request):
    actor=identity(request,cfg,'content:publish')
    campaign=body.campaign.model_dump(mode='json')
    with db(cfg) as conn:
        def effect():
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('campaign-publication',0))")
            prior=conn.execute('SELECT * FROM active_campaign WHERE singleton FOR UPDATE').fetchone()
            revision=prior['revision'] if prior else 0
            if revision!=body.expected_revision:
                raise HTTPException(409,{'message':'Привязка уже изменена','current_revision':revision})
            published=release(conn,campaign['content_release_id'])['bundle']
            problems={p['id']:p for p in published['problems']}
            unit_metadata={uid:u for t in published['topics'].values() for uid,u in t.get('learning_units',{}).items()}
            checks={uid:u for t in published['topics'].values() for uid,u in t.get('diagnostic_checks',{}).items()}
            for pid,b in campaign['problems'].items():
                p=problems.get(pid)
                if (not p or not p.get('family_reviewed') or p['problem_family_id']!=b['family_id']
                        or p['level']!=b['difficulty'] or ('campaign_holdout' if p['pool']=='holdout' else p['pool'])!=b['pool']
                        or (p.get('reward_equivalence_id') or 'problem:'+pid)!=b['reward_equivalence_id']):
                    raise HTTPException(422,'Привязка требует проверенных metadata опубликованного содержания')
            for uid,b in campaign['units'].items():
                u=unit_metadata.get(uid)
                if not u or u['kind']!=b['unit_kind'] or b['content_version']!=campaign['content_release_id']:
                    raise HTTPException(422,'Учебная единица ещё не опубликована')
            for v in campaign['volumes'].values():
                if v['diagnostic_id'] and (v['diagnostic_id'] not in checks or checks[v['diagnostic_id']]['rubric_version']!=v['diagnostic_version']):
                    raise HTTPException(422,'Диагностика ещё не опубликована')
            if any(bid.startswith('M-') for bid in campaign['assessments']):
                training=[p for p in problems.values() if p['pool']=='train']
                families={p['problem_family_id'] for p in training}
                if any(not p.get('family_reviewed') for p in training) or families!=set(campaign['training_family_ids']):
                    raise HTTPException(422,'Для M требуется полный проверенный перечень семейств тренировочного банка')
            digest=hashlib.sha256(canonical(campaign).encode()).hexdigest()
            old=conn.execute('SELECT sha256 FROM campaign_publications WHERE publication_version=%s',(campaign['publication_version'],)).fetchone()
            if old and old['sha256']!=digest:
                raise HTTPException(409,'Неизменяемая публикация уже существует с другим hash')
            conn.execute('INSERT INTO campaign_publications VALUES (%s,%s,%s,now()) ON CONFLICT DO NOTHING',
                         (campaign['publication_version'],Jsonb(campaign),digest))
            conn.execute('''INSERT INTO active_campaign VALUES (true,%s,%s) ON CONFLICT(singleton)
                DO UPDATE SET publication_version=excluded.publication_version,revision=excluded.revision''',(campaign['publication_version'],revision+1))
            emit(conn,cfg,'content.character-campaign.published.v1','owner',campaign['publication_version'],revision+1,
                 campaign,request.state.request_id,source_stream='character-campaign')
            return {'publication_version':campaign['publication_version'],'revision':revision+1,'sha256':digest}
        return command(conn,actor,body,'content.campaign-publish',effect)


@app.get('/internal/content/character-campaign')
def campaign_metadata(request:Request,publication_version:str|None=None):
    identity(request,cfg,'content:protected')
    with db(cfg) as conn:
        row=conn.execute('SELECT bindings FROM campaign_publications WHERE publication_version=%s',(publication_version,)).fetchone() if publication_version else conn.execute('SELECT bindings FROM active_campaign JOIN campaign_publications USING(publication_version)').fetchone()
        if not row:raise HTTPException(409,'BLOCKED_CONTENT: привязка испытаний ещё не опубликована')
        return row['bindings']


@app.get('/internal/content/learning-evidence/{unit_id}')
def evidence_metadata(unit_id:str,request:Request,publication_version:str):
    bindings=campaign_metadata(request,publication_version)
    with db(cfg) as conn:
        published=release(conn,bindings['content_release_id'])['bundle']
        units={uid:u for t in published['topics'].values() for uid,u in t.get('learning_units',{}).items()}
        diagnostics={uid:u for t in published['topics'].values() for uid,u in t.get('diagnostic_checks',{}).items()}
        if unit_id in bindings['units']:
            return {'kind':'learning_unit_completed','binding':bindings['units'][unit_id],
                    'metadata':units[unit_id],'content_release_id':bindings['content_release_id']}
        volume=next(((vid,v) for vid,v in bindings['volumes'].items() if v['diagnostic_id']==unit_id),None)
        if volume:
            return {'kind':'diagnostic_result','binding':{'volume_id':volume[0]},'metadata':diagnostics[unit_id],
                    'content_release_id':bindings['content_release_id']}
        raise HTTPException(404,'Учебная единица не зарегистрирована')


@app.get('/internal/content/assessment/{blueprint_id}')
def assessment_metadata(blueprint_id:str,request:Request,publication_version:str):
    bindings=campaign_metadata(request,publication_version)
    registered=bindings['assessments'].get(blueprint_id)
    if not registered:raise HTTPException(409,'BLOCKED_CONTENT: контрольный комплект ещё не опубликован')
    return {**registered,'blueprint_id':blueprint_id,'weights':[20,25,25,30] if blueprint_id.startswith('K-') else [15]*5+[25],
            'problems':{pid:bindings['problems'][pid] for pid in registered['problem_ids']},'content_release_id':bindings['content_release_id']}


@app.get('/internal/content/assessment/{blueprint_id}/problems/{problem_id}')
def assessment_problem(blueprint_id:str,problem_id:str,request:Request,publication_version:str):
    metadata_=assessment_metadata(blueprint_id,request,publication_version)
    if problem_id not in metadata_['problem_ids']:raise HTTPException(404,'Задача не входит в зарегистрированный комплект')
    with db(cfg) as conn:
        r=release(conn,metadata_['content_release_id'])
        p=next((p for p in r['bundle']['problems'] if p['id']==problem_id and p['pool']=='holdout'),None)
        if not p:raise HTTPException(404,'Контрольное условие недоступно')
        return {'content_release_id':r['release_id'],**visible(p,r['bundle']['topics'],metadata_['problems'][problem_id])}
