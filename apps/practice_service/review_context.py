"""Read-only проекция обязательств scheduler; practice не назначает интервалы."""
import hashlib
from psycopg.types.json import Jsonb
from contracts.events import Event
from platformkit.runtime import db,canonical


def consume(cfg,raw):
    event=Event.model_validate(raw)
    if (event.producer,event.event_type,event.source_stream,event.profile_id)!=('learning-service','learning.review-obligation.registered.v1','review-obligations','owner'):
        raise ValueError('Неизвестный владелец review obligation')
    p=event.payload
    if set(p)!={'obligation_id','owner','problem_id','content_release_id','due_at','last_credited_learning_at','is_scheduler_obligation'} or p['owner']!='learning-service' or p['is_scheduler_obligation'] is not True:
        raise ValueError('Неверное обязательство')
    if p['obligation_id']!=event.aggregate_id:raise ValueError('ID обязательства не совпадает')
    from datetime import datetime
    from uuid import UUID
    UUID(p['obligation_id'])
    for key in ('due_at','last_credited_learning_at'):
        if datetime.fromisoformat(p[key]).tzinfo is None:raise ValueError('Нужен UTC instant')
    digest=hashlib.sha256(canonical(raw).encode()).hexdigest()
    with db(cfg) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('review:'+p['obligation_id'],))
        prior=conn.execute('SELECT * FROM review_inbox WHERE event_id=%s',(event.event_id,)).fetchone()
        if prior:
            if prior['event_hash']!=digest:raise ValueError('Event ID/hash conflict')
            return
        conn.execute('INSERT INTO review_inbox VALUES (%s,%s)',(event.event_id,digest))
        conn.execute('''INSERT INTO review_obligations_projection VALUES (%s,%s,%s) ON CONFLICT(id)
            DO UPDATE SET revision=excluded.revision,doc=excluded.doc WHERE review_obligations_projection.revision<excluded.revision''',
            (event.aggregate_id,event.aggregate_revision,Jsonb(p)))
