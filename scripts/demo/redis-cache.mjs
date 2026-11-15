// Два HTTP-запроса miss/hit и проверка значения в собственном Redis learning.
import {apiClient, python} from './_common.mjs';

const api = await apiClient();
const first = await api('learning', '/progress');
const key = await python('learning', `import json,psycopg,redis
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
c=json.loads(Path('/run/secrets/config').read_text())
with psycopg.connect(c['dsn'],connect_timeout=5) as conn:
 zone=conn.execute("SELECT timezone FROM settings WHERE profile_id='owner'").fetchone()[0]
day=datetime.now(ZoneInfo(zone)).date()
key='learning:owner:'+${JSON.stringify(first.revision)}+':'+str(day)+':summary'
r=redis.Redis.from_url(c['redis_url'],socket_timeout=5,socket_connect_timeout=5)
r.delete(key)
print(key)`);

const miss = await api('learning', '/progress');
const hit = await api('learning', '/progress');
if (miss.cache !== 'miss' || hit.cache !== 'hit') throw new Error('Expected miss then hit');
if (miss.revision !== first.revision || hit.revision !== first.revision) {
    throw new Error('Learning revision changed during the cache check');
}

const cached = JSON.parse(await python('learning', `import json,redis
from pathlib import Path
c=json.loads(Path('/run/secrets/config').read_text())
r=redis.Redis.from_url(c['redis_url'],decode_responses=True,socket_timeout=5,socket_connect_timeout=5)
v=json.loads(r.get(${JSON.stringify(key)}))
print(json.dumps({p:v[p] for p in ['revision','policy_version','generated_at']}))`));
if (cached.revision !== hit.revision || cached.generated_at !== hit.generated_at) {
    throw new Error('Redis value does not match the HTTP response');
}

console.log(JSON.stringify({
    request_1: {http: 200, cache: miss.cache},
    request_2: {http: 200, cache: hit.cache},
    redis_get: cached,
}, null, 2));
