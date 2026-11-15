import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path

import aio_pika
import httpx
import jwt
import psycopg
from fastapi import FastAPI, HTTPException, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger('study')
logging.basicConfig(level=logging.INFO, format='%(message)s')


def now():
    return datetime.now(timezone.utc)


def iso():
    return now().isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)


def config():
    return json.loads(Path(os.environ['CRUCIBLE_CONFIG']).read_text())


@contextmanager
def db(cfg):
    with psycopg.connect(cfg['dsn'], row_factory=dict_row, connect_timeout=3,
                         options='-c statement_timeout=8000 -c lock_timeout=3000') as conn:
        yield conn


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: uuid.UUID


class RevisionCommand(Command):
    expected_revision: int = Field(ge=1)


def identity(request: Request, cfg, scope):
    authorization = request.headers.get('authorization', '')
    token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else request.headers.get('x-session-assertion', '')
    try:
        actor = jwt.decode(token, cfg['public_key'], algorithms=['EdDSA'], audience=cfg['service'],
                           issuer='crucible', options={'require': ['exp', 'sub', 'aud', 'jti']})
    except jwt.PyJWTError:
        raise HTTPException(401, 'Требуется вход')
    if scope not in actor.get('scopes', []):
        raise HTTPException(403, 'Недостаточно полномочий')
    if actor.get('profile_id') != 'owner':
        raise HTTPException(403, 'Неизвестный профиль')
    return actor


def command(conn, actor, body, operation, effect):
    payload = body.model_dump(mode='json')
    key = str(body.command_id)
    digest = hashlib.sha256(canonical({'operation': operation, 'body': payload}).encode()).hexdigest()
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (actor['sub']+key,))
    existing = conn.execute('SELECT * FROM command_receipts WHERE actor=%s AND command_id=%s', (actor['sub'], key)).fetchone()
    if existing:
        if existing['payload_hash'] != digest:
            raise HTTPException(409, 'command_id уже использован с другим содержимым')
        return existing['response']
    result = json.loads(canonical(effect()))
    conn.execute('INSERT INTO command_receipts(actor,command_id,payload_hash,response) VALUES (%s,%s,%s,%s)',
                 (actor['sub'], key, digest, Jsonb(result)))
    log.info(canonical({'service': operation.split('.')[0], 'operation': operation, 'actor': actor['sub'],
                        'command_id': key, 'result': 'transaction_ready', 'at': iso()}))
    return result


def emit(conn, cfg, event_type, profile, aggregate, revision, payload, correlation):
    seq = conn.execute('''INSERT INTO source_stream(profile_id,seq) VALUES (%s,1)
        ON CONFLICT(profile_id) DO UPDATE SET seq=source_stream.seq+1 RETURNING seq''', (profile,)).fetchone()['seq']
    event = {'schema_version': 1, 'event_id': str(uuid.uuid4()), 'event_type': event_type,
             'producer': cfg['service'], 'profile_id': profile, 'source_seq': seq,
             'aggregate_id': str(aggregate), 'aggregate_revision': revision,
             'occurred_at': iso(), 'correlation_id': str(correlation), 'payload': payload}
    if len(canonical(event).encode()) > 512_000:
        raise HTTPException(413, 'Событие слишком большое')
    conn.execute('INSERT INTO outbox(event_id,event) VALUES (%s,%s)', (event['event_id'], Jsonb(event)))
    return seq


def assert_revision(row, expected):
    if not row:
        raise HTTPException(404, 'Запись не найдена')
    if row['revision'] != expected:
        raise HTTPException(409, {'message': 'Запись изменена в другой вкладке', 'current_revision': row['revision']})


def call(cfg, service, path, *, method='GET', payload=None):
    target = cfg['downstreams'][service]
    try:
        response = httpx.request(method, target['url']+path, json=payload,
                                 headers={'Authorization': 'Bearer '+target['token']}, timeout=4)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, f'Сервис {service} временно недоступен')


async def broker_loop(cfg, consume=None):
    delay = 1
    urls = cfg.get('amqp_urls', [cfg['amqp_url']])
    connection_index = 0
    while True:
        try:
            target_url = urls[connection_index % len(urls)]
            connection_index += 1
            connection = await aio_pika.connect(target_url, timeout=5)
            async with connection:
                channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
                await channel.set_qos(prefetch_count=4)
                exchange = await channel.get_exchange('study.events', ensure=False)
                if consume:
                    queue = await channel.get_queue(cfg['queue'], ensure=False)

                    async def handle(message):
                        try:
                            event = json.loads(message.body)
                            if len(message.body) > 512_000 or event['schema_version'] != 1:
                                raise ValueError('Unsupported event')
                            await asyncio.to_thread(consume, event)
                        except (ValueError, KeyError, TypeError):
                            await message.reject(requeue=False)
                            log.warning(canonical({'service': cfg['service'], 'operation': 'consumer.dlq'}))
                        except Exception:
                            await asyncio.sleep(1)
                            await message.nack(requeue=True)
                            log.warning(canonical({'service': cfg['service'], 'operation': 'consumer.retry'}))
                        else:
                            log.info(canonical({'service': cfg['service'], 'operation': 'consumer.committed',
                                'event_id': event.get('event_id'), 'source_seq': event.get('source_seq'),
                                'correlation_id': event.get('correlation_id')}))
                            await message.ack()
                    await queue.consume(handle)
                delay = 1
                while not connection.is_closed and not channel.is_closed:
                    with db(cfg) as conn:
                        rows = conn.execute('SELECT event_id,event FROM outbox WHERE published_at IS NULL ORDER BY created_at,event_id LIMIT 30').fetchall()
                    for row in rows:
                        event = row['event']
                        await exchange.publish(aio_pika.Message(canonical(event).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            message_id=str(row['event_id']), content_type='application/json',
                            correlation_id=event['correlation_id']), routing_key=event['event_type'], mandatory=True, timeout=4)
                        with db(cfg) as conn:
                            conn.execute('UPDATE outbox SET published_at=now(),deliveries=deliveries+1 WHERE event_id=%s', (row['event_id'],))
                        log.info(canonical({'service': cfg['service'], 'operation': 'outbox.confirmed',
                            'event_id': event['event_id'], 'event_type': event['event_type'],
                            'correlation_id': event['correlation_id']}))
                    await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            # Some AMQP futures are cancelled on broker shutdown. They must not silently
            # kill the dispatcher; only cancellation of this owning task ends its lifetime.
            if asyncio.current_task().cancelling():
                raise
            log.warning(canonical({'service': cfg['service'], 'operation': 'broker.cancelled_future_retry'}))
            await asyncio.sleep(delay)
        except Exception as exc:
            log.warning(canonical({'service': cfg['service'], 'operation': 'broker.retry', 'error_type': type(exc).__name__, 'backoff_seconds': delay}))
            await asyncio.sleep(delay)
            delay = min(delay*2, 15)


def app_factory(cfg, consume=None):
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(broker_loop(cfg, consume))
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    app = FastAPI(title=cfg['service'], version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def trace(request, call_next):
        request_id = request.headers.get('x-request-id', '')
        try:
            request_id = str(uuid.UUID(request_id))
        except ValueError:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        if request.headers.get('content-length', '0').isdigit() and int(request.headers.get('content-length', '0')) > 256_000:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        log.info(canonical({'service': cfg['service'], 'operation': request.method+' '+request.url.path,
                            'status': response.status_code, 'correlation_id': request_id, 'at': iso()}))
        return response

    @app.get('/health/live')
    def live():
        return {'service': cfg['service'], 'status': 'live'}

    @app.get('/health/ready')
    def ready():
        try:
            with db(cfg) as conn:
                conn.execute('SELECT 1')
            return {'status': 'ready', 'capabilities': {'own_database': True, 'broker_required_for_local_writes': False}}
        except psycopg.Error:
            raise HTTPException(503, 'Собственная БД недоступна')

    @app.get('/hello')
    def hello():
        return {'message': 'Hello from '+cfg['service']}

    @app.get('/diagnostics')
    def diagnostics(request: Request):
        identity(request, cfg, 'diagnostics:read')
        with db(cfg) as conn:
            return conn.execute('''SELECT count(*) FILTER(WHERE published_at IS NULL) AS pending_outbox,
                extract(epoch from now()-min(created_at) FILTER(WHERE published_at IS NULL)) AS oldest_pending_seconds
                FROM outbox''').fetchone()
    return app
