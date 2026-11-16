import hashlib
import json
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException, Request, Response
from pydantic import Field
from psycopg.types.json import Jsonb
import redis
from contracts.events import Event, PracticeFact
from platformkit.runtime import app_factory, config, db, now, iso, canonical, identity, emit, command, Command, RevisionCommand
from .policy import calculate, make_plan, POLICY_VERSION

cfg = config()
cache = redis.Redis.from_url(cfg['redis_url'], socket_timeout=0.2, socket_connect_timeout=0.2, decode_responses=True)
PREFIX = '/api/v1/learning'


def consume(raw):
    event = Event.model_validate(raw)
    source = {'practice.learning-facts.changed.v1': 'practice', 'content.catalog.published.v1': 'content'}.get(event.event_type)
    if not source:
        raise ValueError('Unexpected event type')
    expected_producer = source+'-service'
    if event.producer != expected_producer or event.profile_id != 'owner':
        raise ValueError('Wrong producer or profile')
    digest = hashlib.sha256(canonical(raw).encode()).hexdigest()
    with db(cfg) as conn:
        cursor = conn.execute('SELECT seq FROM source_cursors WHERE source=%s FOR UPDATE', (source,)).fetchone()['seq']
        prior = conn.execute('SELECT * FROM inbox_receipts WHERE event_id=%s OR (source=%s AND source_seq=%s)', (event.event_id, source, event.source_seq)).fetchone()
        if prior:
            if prior['event_hash'] != digest:
                raise ValueError('Sequence or event ID reused with different payload')
            return
        conn.execute('INSERT INTO inbox_receipts(event_id,source,source_seq,event_hash) VALUES (%s,%s,%s,%s)', (event.event_id, source, event.source_seq, digest))
        if source == 'practice':
            PracticeFact.model_validate(event.payload)
            fact = {**event.payload, 'attempt_id': event.aggregate_id, 'source_seq': event.source_seq}
            conn.execute('''INSERT INTO attempt_facts_projection VALUES (%s,%s,%s)
                ON CONFLICT(attempt_id) DO UPDATE SET revision=excluded.revision,fact=excluded.fact
                WHERE attempt_facts_projection.revision < excluded.revision''', (event.aggregate_id, event.aggregate_revision, Jsonb(fact)))
        else:
            conn.execute('''INSERT INTO catalog_projection(singleton,source_seq,release_id,catalog) VALUES(true,%s,%s,%s)
                ON CONFLICT(singleton) DO UPDATE SET source_seq=excluded.source_seq,release_id=excluded.release_id,catalog=excluded.catalog
                WHERE catalog_projection.source_seq < excluded.source_seq''', (event.source_seq, event.payload['content_release_id'], Jsonb(event.payload['catalog'])))
        while conn.execute('SELECT 1 FROM inbox_receipts WHERE source=%s AND source_seq=%s', (source, cursor+1)).fetchone():
            cursor += 1
        conn.execute('UPDATE source_cursors SET seq=%s WHERE source=%s', (cursor, source))
        emit(conn, cfg, 'learning.progress.updated.v1', 'owner', 'owner', max(1, cursor),
             {'source': source, 'applied_seq': cursor}, event.correlation_id)


app = app_factory(cfg, consume)


def inputs(conn):
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    catalog = conn.execute('SELECT * FROM catalog_projection').fetchone()
    settings = conn.execute("SELECT * FROM settings WHERE profile_id='owner'").fetchone()
    cursors = {r['source']: r['seq'] for r in conn.execute('SELECT * FROM source_cursors').fetchall()}
    facts = [r['fact'] for r in conn.execute('SELECT fact FROM attempt_facts_projection ORDER BY attempt_id').fetchall()]
    return catalog, settings, cursors, facts


@app.get(PREFIX+'/progress')
def progress(request: Request, response: Response, at_least_practice_seq: int = 0):
    identity(request, cfg, 'learning:read')
    with db(cfg) as conn:
        c, s, cursors, facts = inputs(conn)
    at = now()
    revision = hashlib.sha256(canonical([cursors, s, [(f['attempt_id'], f['source_seq']) for f in facts]]).encode()).hexdigest()[:20]
    cache_key = f'learning:owner:{revision}:{at.astimezone(ZoneInfo(s["timezone"])).date()}:summary'
    summary = None
    status = 'miss'
    try:
        cached = cache.get(cache_key)
        if cached:
            summary = json.loads(cached)
            status = 'hit'
    except redis.RedisError:
        status = 'unavailable'
    if summary is None:
        summary = {'skills': calculate(facts, c['catalog'] if c else [], at, s['timezone']),
                   'active_minutes': sum(f['active_minutes'] for f in facts if f['attempt_status'] == 'completed'),
                   'revision': revision, 'policy_version': POLICY_VERSION, 'generated_at': iso()}
        try:
            cache.setex(cache_key, 60, canonical(summary))
        except redis.RedisError:
            status = 'unavailable'
    response.headers['X-Cache'] = status
    return {**summary, 'applied_practice_seq': cursors['practice'], 'catalog_seq': cursors['content'],
            'content_release_id': c['release_id'] if c else None, 'required_practice_seq': at_least_practice_seq,
            'pending': cursors['practice'] < at_least_practice_seq,
            'freshness': 'pending' if cursors['practice'] < at_least_practice_seq else 'at_requested_cursor',
            'cache': status}


@app.get(PREFIX+'/today')
def today(request: Request, at_least_practice_seq: int = 0):
    identity(request, cfg, 'learning:read')
    with db(cfg) as conn:
        c, s, cursors, facts = inputs(conn)
        day = now().astimezone(ZoneInfo(s['timezone'])).date()
        plan = conn.execute("SELECT * FROM daily_plans WHERE profile_id='owner' AND study_date=%s", (day,)).fetchone()
        return {'plan': plan['plan'] if plan else None, 'applied_practice_seq': cursors['practice'],
                'pending': cursors['practice'] < at_least_practice_seq,
                'settings': s, 'catalog_available': bool(c)}


class Plan(Command):
    refresh: bool = False
    expected_revision: int | None = None


@app.post(PREFIX+'/daily-plans')
def daily_plan(body: Plan, request: Request):
    actor = identity(request, cfg, 'learning:write')
    with db(cfg) as conn:
        def effect():
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('plan:owner',0))")
            c = conn.execute('SELECT * FROM catalog_projection').fetchone()
            if not c:
                raise HTTPException(503, 'Каталог ещё не опубликован в learning')
            s = conn.execute("SELECT * FROM settings WHERE profile_id='owner'").fetchone()
            at = now()
            day = at.astimezone(ZoneInfo(s['timezone'])).date()
            prior = conn.execute("SELECT * FROM daily_plans WHERE profile_id='owner' AND study_date=%s FOR UPDATE", (day,)).fetchone()
            if prior and not body.refresh:
                return prior['plan']
            if prior and body.expected_revision != prior['revision']:
                raise HTTPException(409, 'План уже изменён')
            facts = [r['fact'] for r in conn.execute('SELECT fact FROM attempt_facts_projection').fetchall()]
            skills = calculate(facts, c['catalog'], at, s['timezone'])
            cursors = {r['source']: r['seq'] for r in conn.execute('SELECT * FROM source_cursors').fetchall()}
            plan = make_plan(facts, c['catalog'], skills, at, s['daily_count'], s['timezone'], str(day), s['weights'])
            plan.update(id=str(prior['id']) if prior else str(uuid.uuid4()), revision=prior['revision']+1 if prior else 1,
                        content_release_id=c['release_id'], source_revisions=cursors, settings_revision=s['revision'], generated_at=iso())
            from datetime import datetime,time,timezone
            for item in plan['items']:
                previous=[f for f in facts if f['problem_id']==item['id'] and f['eligible_for_progress'] and f['completed_at']]
                if not item.get('review_due') or not previous:continue
                skill=next(skill for skill in skills if skill['skill_id']==item['primary_skill_id'])
                due=datetime.combine(datetime.fromisoformat(skill['due_date']).date(),time(),ZoneInfo(s['timezone'])).astimezone(timezone.utc)
                last=max(f['completed_at'] for f in previous)
                oid=str(uuid.uuid5(uuid.NAMESPACE_URL,plan['id']+':'+str(plan['revision'])+':'+item['id']))
                context={'obligation_id':oid,'owner':'learning-service','problem_id':item['id'],
                    'content_release_id':c['release_id'],'due_at':due.isoformat(),'last_credited_learning_at':last,'is_scheduler_obligation':True}
                conn.execute('INSERT INTO review_obligations VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (oid,'owner',item['id'],c['release_id'],plan['id'],plan['revision'],due,last))
                emit(conn,cfg,'learning.review-obligation.registered.v1','owner',oid,1,context,request.state.request_id,source_stream='review-obligations')
                item['review_obligation_id']=oid
            conn.execute('''INSERT INTO daily_plans VALUES (%s,'owner',%s,%s,%s) ON CONFLICT(profile_id,study_date)
                DO UPDATE SET revision=excluded.revision,plan=excluded.plan''', (plan['id'], day, plan['revision'], Jsonb(plan)))
            conn.execute('INSERT INTO daily_plan_revisions(plan_id,revision,plan) VALUES (%s,%s,%s)',(plan['id'],plan['revision'],Jsonb(plan)))
            return plan
        return command(conn, actor, body, 'learning.plan', effect)


class Settings(RevisionCommand):
    timezone: str = Field(max_length=64)
    daily_count: int = Field(ge=1, le=10)


@app.patch(PREFIX+'/settings')
def settings(body: Settings, request: Request):
    actor = identity(request, cfg, 'learning:write')
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, 'Неизвестный часовой пояс')
    with db(cfg) as conn:
        def effect():
            row = conn.execute("UPDATE settings SET timezone=%s,daily_count=%s,revision=revision+1 WHERE profile_id='owner' AND revision=%s RETURNING *", (body.timezone, body.daily_count, body.expected_revision)).fetchone()
            if not row:
                raise HTTPException(409, 'Настройки изменены')
            conn.execute('INSERT INTO settings_revisions(profile_id,revision,settings) VALUES (%s,%s,%s)',('owner',row['revision'],Jsonb(row)))
            emit(conn,cfg,'learning.character-profile.changed.v1','owner','owner',row['revision'],
                 {'timezone':row['timezone'],'revision':row['revision']},request.state.request_id,source_stream='character-profile')
            return row
        return command(conn, actor, body, 'learning.settings', effect)
