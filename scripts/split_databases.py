"""Перенос существующей daily-установки без удаления исходного PostgreSQL volume."""
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from database_topology import OWNERS, primary, split_configuration
from ops import ASSESSMENT, COMPOSE, compose, container, evidence, host_owned, run

if ASSESSMENT:
    raise SystemExit('Перенос предназначен для daily. Assessment создаёт отдельные синтетические БД.')
root = Path('.secrets')
work = Path('.private/database-split')
work.mkdir(mode=0o700, parents=True, exist_ok=True)
work.chmod(0o700)
host_owned(work)
state_path = work/'state.json'


def save(state):
    temp = state_path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2))
    temp.chmod(0o600)
    host_owned(temp)
    os.replace(temp, state_path)


def fingerprints(command, owner):
    query = """SELECT format('SELECT %L, count(*), md5(coalesce(string_agg(row_to_json(t)::text, chr(10) ORDER BY row_to_json(t)::text), %L)) FROM public.%I t;', tablename, '', tablename)
               FROM pg_tables WHERE schemaname='public' ORDER BY tablename"""
    sql = run(command+['psql', '-U', 'postgres', '-d', owner+'_db', '-Atc', query]).stdout
    return sorted(run(command+['psql', '-U', 'postgres', '-d', owner+'_db', '-Atc', sql]).stdout.splitlines())


if state_path.exists():
    state = json.loads(state_path.read_text())
else:
    if (root/'postgres-content-init.sql').exists():
        raise SystemExit('Конфигурация уже разделена; перенос не требуется.')
    old = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project='+
               json.loads(compose('config', '--format', 'json').stdout)['name'],
               '--filter', 'label=com.docker.compose.service=postgres']).stdout.splitlines()
    if len(old) != 1:
        raise SystemExit('Ожидался один исходный PostgreSQL; ничего не изменено.')
    # Не перезаписываем новый volume, созданный в обход процедуры переноса.
    for owner in OWNERS:
        if compose('ps', '-aq', primary(owner)).stdout.strip():
            raise SystemExit('Новый контейнер уже существует; автоматический перенос остановлен.')
    shutil.copytree(root, work/'original-secrets', ignore=shutil.ignore_patterns('assessment', 'crucible-restore-*'))
    shutil.copytree(work/'original-secrets', work/'staged-secrets')
    split_configuration(work/'staged-secrets')
    state = {'at': datetime.now(timezone.utc).isoformat(), 'source_container': old[0], 'phase': 'staged', 'restored': []}
    save(state)

if state['phase'] == 'verified':
    print('Данные уже перенесены и сверены. Исходный volume сохранён.')
    raise SystemExit(0)
source = ['docker', 'exec', '-i', state['source_container']]
# Повторный вызов после сбоя не допускает новых записей до окончания сверки.
compose('stop', '-t', '30', 'web', *OWNERS, 'content-init', 'migrations')
if state['phase'] == 'staged':
    state['tables'] = {owner: fingerprints(source, owner) for owner in OWNERS}
    state['dumps'] = {}
    for owner in OWNERS:
        path = work/(owner+'.dump')
        with path.open('wb') as stream:
            subprocess.run(source+['pg_dump', '-U', 'postgres', '-d', owner+'_db', '-Fc', '--no-owner'], stdout=stream, check=True)
        path.chmod(0o600)
        host_owned(path)
        state['dumps'][owner] = hashlib.sha256(path.read_bytes()).hexdigest()
    state['phase'] = 'dumped'
    save(state)
if state['phase'] == 'dumped':
    for path in (work/'staged-secrets').iterdir():
        if not path.is_file() or path.name.startswith('.'):
            continue
        temp = root/(path.name+'.split-tmp')
        shutil.copy2(path, temp)
        host_owned(temp)
        os.replace(temp, root/path.name)
    state['phase'] = 'configured'
    save(state)
compose('up', '-d', '--wait', '--wait-timeout', '180', *(primary(o) for o in OWNERS))
for owner in OWNERS:
    path = work/(owner+'.dump')
    if hashlib.sha256(path.read_bytes()).hexdigest() != state['dumps'][owner]:
        raise RuntimeError('Повреждена контрольная копия '+owner)
    target = COMPOSE+['exec', '-T', primary(owner)]
    if owner not in state['restored']:
        with path.open('rb') as stream:
            subprocess.run(target+['pg_restore', '-U', 'postgres', '-d', owner+'_db', '--exit-on-error',
                                   '--clean', '--if-exists', '--no-owner', '--role', owner+'_migration'], stdin=stream, check=True)
        state['restored'].append(owner)
        save(state)
    if fingerprints(target, owner) != state['tables'][owner]:
        raise RuntimeError('Содержимое таблиц не совпало: '+owner+'; приложения остаются остановленными')
run(['docker', 'stop', state['source_container']])
state['phase'] = 'verified'
save(state)
evidence('database-split', {'at': datetime.now(timezone.utc), 'source_container': state['source_container'],
                          'source_volume_retained': True, 'databases': list(OWNERS),
                          'tables_verified': state['tables'], 'dump_sha256': state['dumps']})
print('Четыре БД перенесены; количество и хеши строк всех таблиц совпали. Исходный volume сохранён. Запустите scripts/deploy.')
