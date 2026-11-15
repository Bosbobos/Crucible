import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb
from platformkit.runtime import (app_factory, config, db, now, iso, identity, command, emit,
                                 call, assert_revision, Command, RevisionCommand)

cfg = config()
app = app_factory(cfg)
PREFIX = '/api/v1/practice'
Outcome = Literal['independent', 'assisted', 'reviewed', 'unfinished']


def origin(request):
    if request.headers.get('origin') != cfg['origin']:
        raise HTTPException(403, 'Недопустимый Origin')


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=1, max_length=256)


@app.post(PREFIX+'/auth/login')
def login(body: Login, request: Request, response: Response):
    origin(request)
    # A single-owner global limiter is deliberately conservative, and persists without Redis.
    with db(cfg) as conn:
        limit = conn.execute('''INSERT INTO login_limits(bucket,started_at,attempts) VALUES ('owner',now(),1)
            ON CONFLICT(bucket) DO UPDATE SET
             attempts=CASE WHEN login_limits.started_at < now()-interval '5 minutes' THEN 1 ELSE login_limits.attempts+1 END,
             started_at=CASE WHEN login_limits.started_at < now()-interval '5 minutes' THEN now() ELSE login_limits.started_at END
            RETURNING attempts''').fetchone()
    if limit['attempts'] > 10:
        raise HTTPException(429, 'Слишком много попыток входа; повторите через 5 минут')
    try:
        PasswordHasher().verify(cfg['password_hash'], body.password)
    except VerifyMismatchError:
        raise HTTPException(401, 'Неверный пароль')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with db(cfg) as conn:
        conn.execute('INSERT INTO sessions(token_hash,csrf,expires_at) VALUES (%s,%s,%s)',
                     (hashlib.sha256(token.encode()).hexdigest(), csrf, now()+timedelta(hours=12)))
    response.set_cookie('crucible_session', token, httponly=True, secure=cfg['origin'].startswith('https:'),
                        samesite='strict', max_age=43200, path='/')
    return {'csrf': csrf, 'profile_id': 'owner'}


@app.get('/internal/auth/check')
def check(request: Request, response: Response):
    target = request.headers.get('x-original-uri', '')
    service = next((v for k, v in {'content': 'content-service', 'practice': 'practice-service',
                                  'learning': 'learning-service', 'reports': 'report-worker'}.items()
                    if target.startswith('/api/v1/'+k+'/')), None)
    if not service:
        raise HTTPException(401, 'Неизвестный маршрут')
    auth = request.headers.get('authorization', '')
    if auth.startswith('Bearer '):
        try:
            jwt.decode(auth[7:], cfg['public_key'], algorithms=['EdDSA'], issuer='crucible', audience=service,
                       options={'require': ['exp', 'sub', 'jti', 'aud']})
        except jwt.PyJWTError:
            raise HTTPException(401, 'Недопустимый токен')
        return {'ok': True}
    token = request.cookies.get('crucible_session', '')
    with db(cfg) as conn:
        session = conn.execute('SELECT * FROM sessions WHERE token_hash=%s AND expires_at>now()',
                               (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not session:
        raise HTTPException(401, 'Требуется вход')
    if request.headers.get('x-original-method') not in ['GET', 'HEAD']:
        origin(request)
        if not secrets.compare_digest(session['csrf'], request.headers.get('x-csrf-token', '')):
            raise HTTPException(403, 'Недопустимый CSRF-токен')
    assertion = jwt.encode({'iss': 'crucible', 'sub': 'owner', 'profile_id': 'owner', 'aud': service,
                           'scopes': cfg['owner_scopes'], 'exp': now()+timedelta(seconds=30), 'jti': str(uuid.uuid4())},
                          cfg['private_key'], algorithm='EdDSA')
    response.headers['X-Session-Assertion'] = assertion
    return {'ok': True}


@app.get(PREFIX+'/auth/session')
def session(request: Request):
    identity(request, cfg, 'practice:read')
    token = request.cookies.get('crucible_session', '')
    with db(cfg) as conn:
        row = conn.execute('SELECT csrf FROM sessions WHERE token_hash=%s AND expires_at>now()',
                           (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return {'csrf': row['csrf'] if row else None, 'profile_id': 'owner'}


@app.post(PREFIX+'/auth/logout')
def logout(request: Request, response: Response):
    identity(request, cfg, 'practice:write')
    with db(cfg) as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=%s', (hashlib.sha256(request.cookies.get('crucible_session', '').encode()).hexdigest(),))
    response.delete_cookie('crucible_session', path='/')
    return {'logged_out': True}


def get_attempt(conn, attempt_id, lock=False):
    row = conn.execute('SELECT * FROM attempts WHERE id=%s AND profile_id=%s'+(' FOR UPDATE' if lock else ''),
                       (attempt_id, 'owner')).fetchone()
    if not row:
        raise HTTPException(404, 'Попытка не найдена')
    return row


def tick(doc):
    at = now()
    if doc['state'] == 'running':
        from datetime import datetime
        last = datetime.fromisoformat(doc['heartbeat_at'])
        elapsed = max(0, (at-last).total_seconds())
        seconds = min(elapsed, 45)
        doc['time_segments'].append({'kind': doc['timer_mode'], 'from': last.isoformat(),
                                      'to': at.isoformat(), 'seconds': round(seconds, 3)})
        doc['active_seconds'] += seconds
        if elapsed > 45:
            doc['unconfirmed_seconds'] += elapsed-45
    doc['heartbeat_at'] = at.isoformat()


def learning_fact(doc):
    p = doc['problem']
    return {'problem_id': p['id'], 'content_release_id': p['content_release_id'],
                   'problem_family_id': p['problem_family_id'], 'primary_skill_id': p['primary_skill_id'],
                   'level': p['level'], 'attempt_status': doc['state'], 'completed_at': doc.get('completed_at'),
                   'part_outcomes': doc.get('part_outcomes', []),
                   'mathematical_help_used': any(h['mathematical'] and not h.get('retracted') for h in doc['help']),
                   'active_minutes': round(doc['active_seconds']/60, 4),
                   'eligible_for_progress': doc['state'] == 'completed',
            'active_attempt_id': doc['id'] if doc['state'] in ['running', 'paused'] else None}


def save(conn, doc, request, significant=True):
    doc['revision'] += 1
    if significant:
        payload = learning_fact(doc)
        doc['learning_input_seq'] = emit(conn, cfg, 'practice.learning-facts.changed.v1', 'owner', doc['id'], doc['revision'], payload, request.state.request_id)
    conn.execute('UPDATE attempts SET revision=%s,state=%s,doc=%s WHERE id=%s', (doc['revision'], doc['state'], Jsonb(doc), doc['id']))
    conn.execute('INSERT INTO attempt_revisions(attempt_id,revision,doc) VALUES (%s,%s,%s)', (doc['id'], doc['revision'], Jsonb(doc)))
    return doc


def read(conn, row):
    doc = row['doc']
    reviews = conn.execute('SELECT * FROM reviews WHERE attempt_id=%s ORDER BY created_at', (doc['id'],)).fetchall()
    return {**doc, 'reviews': [{**r, 'stale': r['attempt_revision'] != doc['revision']} for r in reviews],
            'questions': conn.execute('SELECT * FROM questions WHERE attempt_id=%s ORDER BY id', (doc['id'],)).fetchall(),
            'proposals': conn.execute('SELECT * FROM correction_proposals WHERE attempt_id=%s ORDER BY id', (doc['id'],)).fetchall()}


@app.get(PREFIX+'/current')
def current(request: Request):
    identity(request, cfg, 'practice:read')
    with db(cfg) as conn:
        row = conn.execute("SELECT * FROM attempts WHERE profile_id='owner' AND state IN ('running','paused')").fetchone()
        seq = conn.execute("SELECT seq FROM source_stream WHERE profile_id='owner'").fetchone()
        return {'attempt': read(conn, row) if row else None, 'learning_input_seq': seq['seq'] if seq else 0}


@app.get(PREFIX+'/attempts/{attempt_id}')
def attempt(attempt_id: uuid.UUID, request: Request):
    identity(request, cfg, 'practice:read')
    with db(cfg) as conn:
        return read(conn, get_attempt(conn, attempt_id))


@app.get(PREFIX+'/attempts')
def history(request: Request):
    identity(request, cfg, 'practice:read')
    with db(cfg) as conn:
        rows = conn.execute("SELECT doc FROM attempts WHERE profile_id='owner' ORDER BY doc->>'started_at' DESC LIMIT 200").fetchall()
        return {'attempts': [{'id': r['doc']['id'], 'state': r['doc']['state'], 'problem_id': r['doc']['problem']['id'],
                              'title': r['doc']['problem']['title'], 'completed_at': r['doc'].get('completed_at')} for r in rows]}


class Start(Command):
    problem_id: str = Field(max_length=80)
    content_release_id: str = Field(max_length=80)


@app.post(PREFIX+'/attempts')
def start(body: Start, request: Request):
    actor = identity(request, cfg, 'practice:write')
    # The network call precedes the write transaction; receipt replay remains available if content is down.
    with db(cfg) as conn:
        receipt = conn.execute('SELECT response FROM command_receipts WHERE actor=%s AND command_id=%s', (actor['sub'], body.command_id)).fetchone()
        if receipt:
            return command(conn, actor, body, 'practice.start', lambda: None)
    from urllib.parse import quote
    problem = call(cfg, 'content', '/api/v1/content/problems/'+quote(body.problem_id, safe='')+'?release_id='+quote(body.content_release_id, safe=''))
    with db(cfg) as conn:
        def effect():
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('active:owner',0))")
            if conn.execute("SELECT id FROM attempts WHERE profile_id='owner' AND state IN ('running','paused')").fetchone():
                raise HTTPException(409, 'Сначала завершите текущую попытку')
            doc = {'id': str(uuid.uuid4()), 'revision': 0, 'state': 'running', 'problem': problem, 'draft': '',
                   'help': [], 'time_segments': [], 'timer_mode': 'solving', 'active_seconds': 0,
                   'unconfirmed_seconds': 0, 'heartbeat_at': iso(), 'started_at': iso(), 'part_outcomes': []}
            conn.execute('INSERT INTO attempts(id,profile_id,revision,state,doc) VALUES (%s,%s,0,%s,%s)', (doc['id'], 'owner', 'running', Jsonb(doc)))
            return save(conn, doc, request)
        return command(conn, actor, body, 'practice.start', effect)


class Patch(RevisionCommand):
    draft: str | None = Field(default=None, max_length=100000)
    state: Literal['running', 'paused', 'abandoned'] | None = None
    timer_mode: Literal['solving', 'theory', 'assisted'] | None = None


@app.patch(PREFIX+'/attempts/{attempt_id}')
def patch(attempt_id: uuid.UUID, body: Patch, request: Request):
    actor = identity(request, cfg, 'practice:write')
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id, True)
            assert_revision(row, body.expected_revision)
            doc = row['doc']
            if doc['state'] not in ['running', 'paused']:
                raise HTTPException(409, 'Попытка уже завершена')
            tick(doc)
            if body.draft is not None:
                doc['draft'] = body.draft
            if body.state:
                doc['state'] = body.state
            if body.timer_mode:
                doc['timer_mode'] = body.timer_mode
            return save(conn, doc, request, significant=bool(body.state))
        return command(conn, actor, body, 'practice.patch:'+str(attempt_id), effect)


class Part(BaseModel):
    model_config = ConfigDict(extra='forbid')
    part_id: str
    outcome: Outcome


class Complete(RevisionCommand):
    part_outcomes: list[Part] = Field(min_length=1, max_length=20)
    reflection: str = Field(default='', max_length=4000)


@app.post(PREFIX+'/attempts/{attempt_id}/complete')
def complete(attempt_id: uuid.UUID, body: Complete, request: Request):
    actor = identity(request, cfg, 'practice:write')
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id, True)
            assert_revision(row, body.expected_revision)
            doc = row['doc']
            if doc['state'] not in ['running', 'paused']:
                raise HTTPException(409, 'Попытка уже завершена')
            expected = {p['id'] for p in doc['problem']['parts']}
            if len(body.part_outcomes) != len(expected) or {p.part_id for p in body.part_outcomes} != expected:
                raise HTTPException(422, 'Оцените каждый подпункт ровно один раз')
            if any(h['mathematical'] and not h.get('retracted') for h in doc['help']) and any(p.outcome == 'independent' for p in body.part_outcomes):
                raise HTTPException(422, 'Математическая помощь уже отмечена; выберите оценку с помощью')
            tick(doc)
            doc.update(state='completed', completed_at=iso(), reflection=body.reflection)
            doc['part_outcomes'] = [{**p.model_dump(), 'skill_id': next(x['skill_id'] for x in doc['problem']['parts'] if x['id'] == p.part_id)} for p in body.part_outcomes]
            return save(conn, doc, request)
        return command(conn, actor, body, 'practice.complete:'+str(attempt_id), effect)


class Help(RevisionCommand):
    kind: Literal['h1', 'h2', 'h3', 'solution', 'core', 'theory', 'tutoring', 'translation']
    topic_id: str | None = Field(default=None,max_length=100)


@app.post(PREFIX+'/attempts/{attempt_id}/help')
def help_attempt(attempt_id: uuid.UUID, body: Help, request: Request):
    actor = identity(request, cfg, 'practice:help')
    with db(cfg) as conn:
        receipt = conn.execute('SELECT response FROM command_receipts WHERE actor=%s AND command_id=%s', (actor['sub'], body.command_id)).fetchone()
        if receipt:
            return command(conn, actor, body, 'practice.help:'+str(attempt_id), lambda: None)
        row = get_attempt(conn, attempt_id)
        assert_revision(row, body.expected_revision)
        doc = row['doc']
    material = None
    if body.kind in ['h1', 'h2', 'h3', 'solution']:
        from urllib.parse import quote
        material = call(cfg, 'content', '/internal/content/protected/'+quote(doc['problem']['id'], safe='')+'/'+body.kind+'?release_id='+quote(doc['problem']['content_release_id'], safe=''))
    elif body.kind in ['core','theory']:
        from urllib.parse import quote
        target=body.topic_id or doc['problem'].get('topic_id')
        if not target:
            raise HTTPException(404,'Для этой задачи в исходном vault нет конспекта')
        material = call(cfg, 'content', '/api/v1/content/topics/'+quote(target,safe='')+'/'+body.kind+'?release_id='+quote(doc['problem']['content_release_id'],safe=''))
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id, True)
            assert_revision(row, body.expected_revision)
            doc = row['doc']
            if doc['state'] == 'abandoned':
                raise HTTPException(409, 'Попытка прервана')
            if doc['state'] != 'completed':
                tick(doc)
                doc['help'].append({'id': str(uuid.uuid4()), 'kind': body.kind, 'at': iso(), 'mathematical': body.kind != 'translation'})
                doc['timer_mode'] = 'theory' if body.kind in ['core', 'theory'] else 'assisted'
                save(conn, doc, request)
            return {'attempt': doc, 'material': material}
        return command(conn, actor, body, 'practice.help:'+str(attempt_id), effect)


class Question(RevisionCommand):
    text: str = Field(min_length=1, max_length=8000)


@app.post(PREFIX+'/attempts/{attempt_id}/questions')
def question(attempt_id: uuid.UUID, body: Question, request: Request):
    actor = identity(request, cfg, 'practice:write')
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id, True)
            assert_revision(row, body.expected_revision)
            qid = str(uuid.uuid4())
            conn.execute('INSERT INTO questions(id,attempt_id,text) VALUES (%s,%s,%s)', (qid, attempt_id, body.text))
            return {'question_id': qid}
        return command(conn, actor, body, 'practice.question:'+str(attempt_id), effect)


@app.get(PREFIX+'/review-queue')
def queue(request: Request):
    identity(request, cfg, 'practice:read')
    with db(cfg) as conn:
        return {'questions': conn.execute("SELECT * FROM questions WHERE status<>'resolved' ORDER BY id LIMIT 100").fetchall()}


class Review(RevisionCommand):
    text: str = Field(min_length=1, max_length=16000)


@app.post(PREFIX+'/attempts/{attempt_id}/reviews')
def review(attempt_id: uuid.UUID, body: Review, request: Request):
    actor = identity(request, cfg, 'review:append')
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id)
            if not conn.execute('SELECT 1 FROM attempt_revisions WHERE attempt_id=%s AND revision=%s', (attempt_id, body.expected_revision)).fetchone():
                raise HTTPException(409, 'Неизвестная редакция попытки')
            rid = str(uuid.uuid4())
            conn.execute('INSERT INTO reviews(id,attempt_id,attempt_revision,actor,text) VALUES (%s,%s,%s,%s,%s)', (rid, attempt_id, body.expected_revision, actor['sub'], body.text))
            return {'review_id': rid, 'stale': row['revision'] != body.expected_revision}
        return command(conn, actor, body, 'practice.review:'+str(attempt_id), effect)


class Proposal(RevisionCommand):
    outcome: Outcome
    reason: str = Field(min_length=1, max_length=4000)


@app.post(PREFIX+'/attempts/{attempt_id}/proposals')
def proposal(attempt_id: uuid.UUID, body: Proposal, request: Request):
    actor = identity(request, cfg, 'correction:propose')
    with db(cfg) as conn:
        def effect():
            row = get_attempt(conn, attempt_id)
            assert_revision(row, body.expected_revision)
            if row['state'] != 'completed':
                raise HTTPException(409, 'Исправление результата доступно после завершения')
            pid = str(uuid.uuid4())
            conn.execute('INSERT INTO correction_proposals(id,attempt_id,expected_revision,outcome,reason) VALUES (%s,%s,%s,%s,%s)', (pid, attempt_id, body.expected_revision, body.outcome, body.reason))
            return {'proposal_id': pid, 'status': 'pending'}
        return command(conn, actor, body, 'practice.propose:'+str(attempt_id), effect)


@app.post(PREFIX+'/proposals/{proposal_id}/approve')
def approve(proposal_id: uuid.UUID, body: Command, request: Request):
    actor = identity(request, cfg, 'correction:approve')
    with db(cfg) as conn:
        def effect():
            p = conn.execute('SELECT * FROM correction_proposals WHERE id=%s FOR UPDATE', (proposal_id,)).fetchone()
            if not p:
                raise HTTPException(404, 'Предложение не найдено')
            if p['status'] != 'pending':
                raise HTTPException(409, 'Предложение уже рассмотрено')
            row = get_attempt(conn, p['attempt_id'], True)
            assert_revision(row, p['expected_revision'])
            doc = row['doc']
            if p['outcome'] == 'independent' and any(h['mathematical'] and not h.get('retracted') for h in doc['help']):
                raise HTTPException(422, 'Сначала требуется отдельное исправление факта помощи')
            for part in doc['part_outcomes']:
                part['outcome'] = p['outcome']
            doc['correction_reason'] = p['reason']
            save(conn, doc, request)
            conn.execute("UPDATE correction_proposals SET status='approved' WHERE id=%s", (proposal_id,))
            return doc
        return command(conn, actor, body, 'practice.approve:'+str(proposal_id), effect)


class Resolve(RevisionCommand):
    status: Literal['open', 'needs_followup', 'resolved']


@app.patch(PREFIX+'/questions/{question_id}')
def resolve(question_id: uuid.UUID, body: Resolve, request: Request):
    actor = identity(request, cfg, 'question:resolve')
    with db(cfg) as conn:
        def effect():
            q = conn.execute('SELECT * FROM questions WHERE id=%s FOR UPDATE', (question_id,)).fetchone()
            assert_revision(q, body.expected_revision)
            conn.execute('UPDATE questions SET status=%s,revision=revision+1 WHERE id=%s', (body.status, question_id))
            return {'status': body.status, 'revision': q['revision']+1}
        return command(conn, actor, body, 'practice.resolve:'+str(question_id), effect)


@app.get('/internal/practice/snapshot')
def snapshot(request: Request):
    identity(request, cfg, 'practice:snapshot')
    with db(cfg) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        seq = conn.execute("SELECT seq FROM source_stream WHERE profile_id='owner'").fetchone()
        return {'practice_seq': seq['seq'] if seq else 0,
                'attempts': [read(conn, r) for r in conn.execute("SELECT * FROM attempts WHERE profile_id='owner' ORDER BY id").fetchall()]}


@app.get('/internal/practice/learning-facts')
def facts_snapshot(request: Request):
    identity(request, cfg, 'practice:facts')
    with db(cfg) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        seq=conn.execute("SELECT seq FROM source_stream WHERE profile_id='owner'").fetchone()
        docs=[r['doc'] for r in conn.execute("SELECT doc FROM attempts WHERE profile_id='owner' ORDER BY id").fetchall()]
        return {'practice_seq':seq['seq'] if seq else 0,'facts':[{'attempt_id':d['id'],'revision':d['revision'],
                'source_seq':d['learning_input_seq'],'fact':learning_fact(d)} for d in docs]}
