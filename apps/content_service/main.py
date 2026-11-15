import hashlib
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError
from contracts.content import ContentBundle
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


def visible(problem,topics):
    return {**metadata(problem), **{k: problem[k] for k in ['statement', 'parts', 'prerequisites', 'revision', 'provenance']},
            'materials':availability(topics.get(problem['topic_id'],{}))}


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
        return {'content_release_id': r['release_id'], **visible(p,r['bundle']['topics'])}


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
