// Новое задание экспорта через API и корреляция outbox/receipt в собственной БД reports.
import {randomUUID} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {apiClient, python} from './_common.mjs';

const api = await apiClient();
const job = await api('reports', '/jobs', 'POST', {command_id: randomUUID()});
let result;
for (let n = 0; n < 120; n++) {
    result = await api('reports', '/jobs/' + job.job_id);
    if (result.status === 'ready') break;
    await delay(250);
}
if (result.status !== 'ready') throw new Error('Export did not complete');

console.log(await python('reports', `import json,psycopg
from pathlib import Path
c=json.loads(Path('/run/secrets/config').read_text())
with psycopg.connect(c['dsn'],connect_timeout=5) as conn:
 row=conn.execute("SELECT o.event_id,o.event->>'event_type',o.published_at IS NOT NULL,i.event_id IS NOT NULL FROM outbox o LEFT JOIN inbox_receipts i ON i.event_id=o.event_id WHERE o.event->>'aggregate_id'=%s AND o.event->>'event_type'='report.requested.v1'",(${JSON.stringify(job.job_id)},)).fetchone()
 if not row or not all(row[2:]):
  raise RuntimeError('Publisher confirmation or consumer receipt is missing')
 status=conn.execute('SELECT status FROM jobs WHERE id=%s',(${JSON.stringify(job.job_id)},)).fetchone()[0]
 if status!='ready': raise RuntimeError('Export is not ready in the database')
 print('event_id:',row[0])
 print('event_type:',row[1])
 print('publisher confirmed:',row[2])
 print('consumer receipt:',row[3])
 print('job status:',status)`));
