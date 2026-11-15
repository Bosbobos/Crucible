"""Rebuild only owned derived projections from scoped owner APIs, in maintenance mode."""
from psycopg.types.json import Jsonb
from platformkit.runtime import config,call,db,emit
from contracts.events import PracticeFact
import uuid

cfg=config()
practice=call(cfg,'practice','/internal/practice/learning-facts')
content=call(cfg,'content','/api/v1/content/catalog')
for row in practice['facts']:PracticeFact.model_validate(row['fact'])
with db(cfg) as conn:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('projection-rebuild',0))")
    conn.execute('DELETE FROM attempt_facts_projection')
    conn.execute('DELETE FROM inbox_receipts')
    for row in practice['facts']:
        fact={**row['fact'],'attempt_id':row['attempt_id'],'source_seq':row['source_seq']}
        conn.execute('INSERT INTO attempt_facts_projection VALUES (%s,%s,%s)',(row['attempt_id'],row['revision'],Jsonb(fact)))
    conn.execute('''INSERT INTO catalog_projection VALUES (true,%s,%s,%s) ON CONFLICT(singleton)
        DO UPDATE SET source_seq=excluded.source_seq,release_id=excluded.release_id,catalog=excluded.catalog''',
        (content['catalog_seq'],content['content_release_id'],Jsonb(content['problems'])))
    conn.execute("UPDATE source_cursors SET seq=%s WHERE source='practice'",(practice['practice_seq'],))
    conn.execute("UPDATE source_cursors SET seq=%s WHERE source='content'",(content['catalog_seq'],))
    emit(conn,cfg,'learning.progress.updated.v1','owner','owner',max(1,practice['practice_seq']),
         {'source':'rebuild','applied_seq':practice['practice_seq']},uuid.uuid4())
print('Rebuilt facts/catalog/cursors. Preserved settings, historical plans and command receipts.')
