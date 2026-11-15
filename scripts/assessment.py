"""Operator-controlled, synthetic-only fault drills with fencing and recovery evidence."""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from ops import ASSESSMENT, SECRETS, compose, run, container, evidence, api_base_url, writable_databases
from database_topology import OWNERS, primary, standby
import os
from bundle_content import bundle

if not ASSESSMENT:raise SystemExit('Use CRUCIBLE_ASSESSMENT=1; this command never targets the daily project.')
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['enable','postgres-failover','rejoin','rabbit-failover','status']);parser.add_argument('--service',choices=OWNERS,default='practice');args=parser.parse_args()
pnode=primary(args.service);snode=standby(args.service)
operator=json.loads((SECRETS/'operator.json').read_text())


def command(**kw):return {'command_id':str(uuid.uuid4()),**kw}


def api(service,path,method='GET',body=None,timeout=50):
    if os.getenv('CRUCIBLE_OPERATOR_CONTAINER')=='1' and not operator.get('_container_url'):
        operator['base_url']=api_base_url();operator['_container_url']=True
    deadline=time.monotonic()+timeout
    while True:
        try:
            r=httpx.request(method,operator['base_url']+'/api/v1/'+service+path,json=body,
                            headers={'Authorization':'Bearer '+operator['tokens'][service]},timeout=8)
            if r.status_code<500:r.raise_for_status();return r.json()
        except httpx.TransportError:pass
        if time.monotonic()>deadline:raise RuntimeError('API unavailable: '+service+path)
        time.sleep(.3)


def pg(service,query):return compose('exec','-T',service,'psql','-v','ON_ERROR_STOP=1','-U','postgres','-Atc',query).stdout.strip()


def rabbit(service,*args):
    return compose('exec','-T',service,'bash','-c','export RABBITMQ_ERLANG_COOKIE="$(cat /run/secrets/erlang_cookie)"; exec "$@"','crucible',*args).stdout


def queues(service='rabbitmq'):return json.loads(rabbit(service,'rabbitmqctl','list_queues','-p','study','name','type','leader','members','--formatter','json'))


def until(fn,timeout=45):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=fn()
            if value:return value
        except (RuntimeError,httpx.HTTPError):pass
        time.sleep(.3)
    raise RuntimeError('Timed out waiting for recovery')


def synchronized(primary,name):
    pg(primary,"ALTER SYSTEM SET synchronous_standby_names = 'FIRST 1 ("+name+")'")
    pg(primary,'SELECT pg_reload_conf()')
    return until(lambda:pg(primary,"SELECT sync_state FROM pg_stat_replication WHERE application_name='"+name+"'")=='sync')


def active():
    a=api('practice','/current')['attempt']
    if not a:
        c=api('content','/catalog');p=c['problems'][0]
        a=api('practice','/attempts','POST',command(problem_id=p['id'],content_release_id=c['content_release_id']))
    return a


def caught_up(seq):return until(lambda:not api('learning','/progress?at_least_practice_seq='+str(seq))['pending'])


def write_owner(owner):
    """Подтверждаем новую авторизованную запись именно в переключённом домене."""
    if owner=='content':
        result=api('content','/releases','POST',command(bundle=bundle()))
        return {'route':'POST /content/releases','release_id':result['release_id']}
    if owner=='practice':
        attempt=active()
        result=api('practice','/attempts/'+attempt['id'],'PATCH',command(expected_revision=attempt['revision'],draft=attempt['draft']+'\nSynthetic owner write after promotion'))
        return {'route':'PATCH /practice/attempts','revision':result['revision']}
    if owner=='learning':
        current=api('learning','/today')['settings']
        result=api('learning','/settings','PATCH',command(expected_revision=current['revision'],timezone=current['timezone'],daily_count=current['daily_count']))
        return {'route':'PATCH /learning/settings','revision':result['revision']}
    result=api('reports','/jobs','POST',command())
    return {'route':'POST /reports/jobs','job_id':result['job_id']}


if args.action=='enable':
    for node in ['rabbit@rabbitmq2','rabbit@rabbitmq3']:
        print(rabbit('rabbitmq','rabbitmq-queues','grow',node,'all','--vhost-pattern','^study$','--membership','voter').strip())
    q=queues();assert all(len(x['members'])==3 for x in q)
    primaries=writable_databases()
    for owner,node in primaries.items():
        synchronized(node,'crucible_standby' if node==primary(owner) else 'crucible_rejoined')
    publication=api('content','/releases','POST',command(bundle=bundle()))
    until(lambda:api('learning','/progress')['content_release_id']==publication['release_id'])
    evidence('assessment-enabled',{'at':datetime.now(timezone.utc),'queues':q,
        'replication':{owner:pg(node,"SELECT application_name||':'||state||':'||sync_state FROM pg_stat_replication") for owner,node in primaries.items()},
        'postgres_version':pg(primaries['practice'],'SHOW server_version')})
    print('Synchronous PostgreSQL replication and 3-member quorum queues verified.')
elif args.action=='postgres-failover':
    assert pg(pnode,'SELECT pg_is_in_recovery()')=='f'
    assert pg(snode,'SELECT pg_is_in_recovery()')=='t'
    assert pg(pnode,"SELECT sync_state FROM pg_stat_replication WHERE application_name='crucible_standby'")=='sync'
    marker=str(uuid.uuid4())
    pg(pnode,"CREATE SCHEMA IF NOT EXISTS assessment; CREATE TABLE IF NOT EXISTS assessment.markers(id text PRIMARY KEY)")
    pg(pnode,"INSERT INTO assessment.markers VALUES ('"+marker+"')")
    a=active();before=api('practice','/attempts/'+a['id'])
    started=time.monotonic();compose('kill','-s','SIGKILL',pnode);compose('stop',pnode)
    fenced=json.loads(run(['docker','inspect',container(pnode)]).stdout)[0]['State']['Running'] is False
    assert fenced
    compose('exec','-T','--user','postgres',snode,'pg_ctl','-D','/var/lib/postgresql/data','promote','-w')
    until(lambda:pg(snode,'SELECT pg_is_in_recovery()')=='f')
    assert pg(snode,"SELECT count(*) FROM assessment.markers WHERE id='"+marker+"'")=='1'
    survived=api('practice','/attempts/'+a['id']);assert survived['draft']==before['draft']
    own_write=write_owner(args.service)
    rto=time.monotonic()-started
    survived=api('practice','/attempts/'+a['id'])
    patch=command(expected_revision=survived['revision'],draft=survived['draft']+'\nSynthetic write after promotion')
    updated=api('practice','/attempts/'+a['id'],'PATCH',patch)
    completed=api('practice','/attempts/'+a['id']+'/complete','POST',command(expected_revision=updated['revision'],
                   part_outcomes=[{'part_id':p['id'],'outcome':'assisted'} for p in updated['problem']['parts']]))
    caught_up(completed['learning_input_seq'])
    job=api('reports','/jobs','POST',command())
    until(lambda:api('reports','/jobs/'+job['job_id'])['status']=='ready')
    evidence('postgres-failover-'+args.service,{'at':datetime.now(timezone.utc),'service':args.service,'marker':marker,'owner_api_write':own_write,'primary_fenced':fenced,'promoted':snode,'attempt_id':a['id'],
                                  'preserved_revision':before['revision'],'new_revision':updated['revision'],'write_rto_seconds':rto,
                                  'learning_caught_up':True,'export_job':job['job_id'],'rpo_confirmed_marker_loss':0})
    print(f'Fenced old primary; promoted standby; new write in {rto:.2f}s; learning and export completed.')
elif args.action=='rejoin':
    assert pg(snode,'SELECT pg_is_in_recovery()')=='f'
    # A promoted standby must permit the reverse replication connection as well.
    compose('exec','-T','--user','postgres',snode,'bash','-c',
            "grep -q '^host replication replicator' /var/lib/postgresql/data/pg_hba.conf || printf '\\nhost replication replicator all scram-sha-256\\n' >> /var/lib/postgresql/data/pg_hba.conf")
    pg(snode,'SELECT pg_reload_conf()')
    already_running=json.loads(run(['docker','inspect',container(pnode)]).stdout)[0]['State']['Running']
    if already_running:
        assert pg(pnode,'SELECT pg_is_in_recovery()')=='t'
    script='''set -eu
export PGPASSWORD="$(cat /run/secrets/pg_admin)"
# The old container was verified stopped above. SIGKILL leaves its stale PID 1 lock;
# the one-off recovery container also has PID 1, so PostgreSQL cannot infer staleness.
rm -f -- /var/lib/postgresql/data/postmaster.pid
method=existing-standby
if [ ! -f /var/lib/postgresql/data/standby.signal ] || ! grep -q 'application_name=crucible_rejoined' /var/lib/postgresql/data/postgresql.auto.conf; then
  if pg_rewind --target-pgdata=/var/lib/postgresql/data --source-server="host=${REJOIN_HOST:?} user=postgres dbname=postgres" --progress; then
    method=pg_rewind
  else
    # При утраченном WAL не запускаем частично перемотанный старый primary.
    # Сначала получаем и проверяем новый независимый physical backup текущего primary.
    stage=$(mktemp -d /var/lib/postgresql/data/.rejoin-stage.XXXXXX)
    export PGPASSWORD="$(cat /run/secrets/replication_password)"
    pg_basebackup -d "host=${REJOIN_HOST:?} port=5432 user=replicator application_name=crucible_rejoined" -D "$stage" -R -X stream --checkpoint=fast
    pg_verifybackup "$stage"
    # Прежний каталог сохраняем внутри того же закрытого volume для разбора.
    previous=/var/lib/postgresql/data/.pre-rejoin-$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -m 700 "$previous"
    find /var/lib/postgresql/data -mindepth 1 -maxdepth 1 ! -path "$stage" ! -path "$previous" -exec mv -t "$previous" -- {} +
    # Только после успешной проверки копии устанавливаем её как новый PGDATA.
    find "$stage" -mindepth 1 -maxdepth 1 -exec mv -t /var/lib/postgresql/data -- {} +
    rmdir "$stage"
    method=verified-basebackup
  fi
fi
touch /var/lib/postgresql/data/standby.signal
printf "\\nprimary_conninfo = 'host=%s port=5432 user=replicator password=%s application_name=crucible_rejoined'\\nsynchronous_standby_names = ''\\n" "${REJOIN_HOST:?}" "$(cat /run/secrets/replication_password)" >> /var/lib/postgresql/data/postgresql.auto.conf
printf 'CRUCIBLE_REJOIN_METHOD=%s\\n' "$method"
'''
    rejoin_method='already-running-standby'
    if not already_running:
        output=compose('run','--rm','--no-deps','--user','postgres','--entrypoint','bash','-e','REJOIN_HOST='+snode,pnode,'-c',script).stdout
        rejoin_method=next(line.split('=',1)[1] for line in output.splitlines() if line.startswith('CRUCIBLE_REJOIN_METHOD='))
        compose('up','-d','--no-deps',pnode)
    until(lambda:pg(pnode,'SELECT pg_is_in_recovery()')=='t')
    synchronized(snode,'crucible_rejoined')
    retained=compose('exec','-T','--user','postgres',pnode,'find','/var/lib/postgresql/data',
                     '-mindepth','1','-maxdepth','1','-type','d','-name','.pre-rejoin-*').stdout.strip().splitlines()
    evidence('postgres-rejoin-'+args.service,{'at':datetime.now(timezone.utc),'service':args.service,'old_primary_role':'standby','new_primary':snode,
                                'method':rejoin_method,'old_pgdata_retained':bool(retained),
                                'retained_pgdata_archives':[Path(name).name for name in retained],
                                'archive_created_this_run':rejoin_method=='verified-basebackup',
                                'replication':pg(snode,"SELECT application_name||':'||state||':'||sync_state FROM pg_stat_replication")})
    print('Old primary safely rejoined as synchronous standby via '+rejoin_method+'.')
elif args.action=='rabbit-failover':
    before=queues();assert all(len(q['members'])==3 for q in before)
    leader=next(q['leader'] for q in before if q['name']=='learning.in');service=leader.split('@')[1]
    observer=next(s for s in ['rabbitmq','rabbitmq2','rabbitmq3'] if s!=service)
    started=time.monotonic();compose('kill','-s','SIGKILL',service)
    try:
        after=until(lambda:[q for q in queues(observer) if q['name']=='learning.in' and q['leader']!=leader])
        a=active()
        result=api('practice','/attempts/'+a['id']+'/complete','POST',command(expected_revision=a['revision'],
                part_outcomes=[{'part_id':p['id'],'outcome':'assisted'} for p in a['problem']['parts']]))
        caught_up(result['learning_input_seq'])
        evidence('rabbit-failover',{'at':datetime.now(timezone.utc),'leader_before':leader,'leader_after':after[0]['leader'],
                                    'queues_before':before,'delivery_resumed_seconds':time.monotonic()-started,
                                    'applied_practice_seq':result['learning_input_seq']})
        print('Quorum elected a new leader and applied a new user result.')
    finally:
        compose('start',service)
        # start подтверждает запуск контейнера, но Rabbit app ещё может загружаться.
        until(lambda:rabbit(service,'rabbitmq-diagnostics','-q','check_running') is not None)
else:
    print(json.dumps({'queues':queues(),'databases':{owner:{'primary_node':primary(owner),'primary_recovery':pg(primary(owner),'SELECT pg_is_in_recovery()'),'standby_node':standby(owner),'standby_recovery':pg(standby(owner),'SELECT pg_is_in_recovery()')} for owner in OWNERS}},indent=2))
