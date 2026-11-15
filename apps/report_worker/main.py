import hashlib
import uuid
from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb
from contracts.events import Event
from platformkit.runtime import config, db, call, canonical, iso, app_factory, identity, command, emit, Command

cfg = config()
PREFIX = '/api/v1/reports'


def consume(raw):
    event = Event.model_validate(raw)
    if event.profile_id != 'owner':
        raise ValueError('Wrong profile')
    if event.event_type == 'report.ready.v1' and event.producer == 'report-worker':
        with db(cfg) as conn:
            conn.execute('INSERT INTO inbox_receipts(event_id) VALUES (%s) ON CONFLICT DO NOTHING', (event.event_id,))
        return
    if event.event_type == 'learning.progress.updated.v1' and event.producer == 'learning-service':
        with db(cfg) as conn:
            if conn.execute('INSERT INTO inbox_receipts(event_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING event_id', (event.event_id,)).fetchone():
                conn.execute("UPDATE jobs SET stale=true WHERE status='ready'")
        return
    if event.event_type != 'report.requested.v1' or event.producer != 'report-worker':
        raise ValueError('Wrong report event')
    with db(cfg) as conn:
        if conn.execute('SELECT 1 FROM inbox_receipts WHERE event_id=%s', (event.event_id,)).fetchone():
            return
    snapshot = call(cfg, 'practice', '/internal/practice/snapshot')
    progress = call(cfg, 'learning', '/api/v1/learning/progress?at_least_practice_seq='+str(snapshot['practice_seq']))
    if progress['pending']:
        raise RuntimeError('Learning projection is pending')
    artifact = {'schema_version': 1, 'kind': 'study-export', 'generated_at': iso(), 'practice': snapshot, 'learning': progress}
    markdown = ['# Итог подготовки', '', f'Попыток: {len(snapshot["attempts"])}', f'Минут: {progress["active_minutes"]}', '']
    for a in snapshot['attempts']:
        markdown += ['## '+a['problem']['id'], a['problem']['statement'], '', a['draft'], '']
    artifact['markdown'] = '\n'.join(markdown)
    manifest = {'schema_version': 1, 'generated_at': artifact['generated_at'],
                'source_versions': {'practice_seq': snapshot['practice_seq'], 'learning_applied_practice_seq': progress['applied_practice_seq'],
                                    'learning_revision': progress['revision'], 'content_release_ids': sorted({a['problem']['content_release_id'] for a in snapshot['attempts']})},
                'sha256': hashlib.sha256(canonical(artifact).encode()).hexdigest(),
                'consistency': 'versioned snapshots; not a global transaction'}
    with db(cfg) as conn:
        if not conn.execute('INSERT INTO inbox_receipts(event_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING event_id', (event.event_id,)).fetchone():
            return
        if not conn.execute("UPDATE jobs SET status='ready',artifact=%s,manifest=%s WHERE id=%s AND profile_id='owner' RETURNING id", (Jsonb(artifact), Jsonb(manifest), event.aggregate_id)).fetchone():
            raise ValueError('Unknown job')
        emit(conn, cfg, 'report.ready.v1', 'owner', event.aggregate_id, 1, {'job_id': event.aggregate_id, 'checksum': manifest['sha256']}, event.correlation_id)


app = app_factory(cfg, consume)


@app.post(PREFIX+'/jobs')
def request_export(body: Command, request: Request):
    actor = identity(request, cfg, 'reports:write')
    with db(cfg) as conn:
        def effect():
            job_id = str(uuid.uuid4())
            conn.execute("INSERT INTO jobs(id,profile_id,status) VALUES (%s,'owner','queued')", (job_id,))
            emit(conn, cfg, 'report.requested.v1', 'owner', job_id, 1, {'job_id': job_id}, request.state.request_id)
            return {'job_id': job_id, 'status': 'queued'}
        return command(conn, actor, body, 'reports.request', effect)


@app.get(PREFIX+'/jobs/{job_id}')
def job(job_id: uuid.UUID, request: Request):
    identity(request, cfg, 'reports:read')
    with db(cfg) as conn:
        row = conn.execute("SELECT id,status,created_at,manifest,stale FROM jobs WHERE id=%s AND profile_id='owner'", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Задание не найдено')
        return row


@app.get(PREFIX+'/jobs/{job_id}/artifact')
def artifact(job_id: uuid.UUID, request: Request):
    identity(request, cfg, 'reports:read')
    with db(cfg) as conn:
        row = conn.execute("SELECT artifact,manifest,stale FROM jobs WHERE id=%s AND profile_id='owner' AND status='ready'", (job_id,)).fetchone()
        if not row:
            raise HTTPException(409, 'Экспорт ещё не готов')
        return row
