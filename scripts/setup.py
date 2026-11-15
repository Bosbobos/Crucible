"""Одноразовая генерация и проверка конфигурации; секреты не выводятся."""
import base64
import fcntl
import hashlib
import json
import os
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from argon2 import PasswordHasher
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import jwt
from urllib.parse import urlsplit
from database_topology import init_sql, primary

SERVICES = {'content': 'content-service', 'practice': 'practice-service',
            'learning': 'learning-service', 'reports': 'report-worker'}
REQUIRED = {'owner-password', 'migrations.json',
            'redis.conf', 'rabbit-definitions.json', 'mcp.json', 'operator.json',
            'test-owner.json', *(name+'.json' for name in SERVICES),
            *(f'pg-{name}-admin' for name in SERVICES),
            *(f'postgres-{name}-init.sql' for name in SERVICES)}


def validate(directory):
    if directory.stat().st_mode & 0o077:
        raise ValueError('Каталог секретов должен иметь права 0700; файлы сохранены')
    missing = sorted(name for name in REQUIRED if not (directory/name).is_file())
    if missing:
        raise ValueError('Неполная конфигурация: отсутствуют '+', '.join(missing))
    for name in REQUIRED:
        path = directory/name
        if path.is_symlink() or not path.read_bytes():
            raise ValueError('Пустой файл или symlink: '+name)
    try:
        configs = {name: json.loads((directory/(name+'.json')).read_text()) for name in SERVICES}
        practice = configs['practice']
        key = serialization.load_pem_private_key(practice['private_key'].encode(), password=None)
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        PasswordHasher().verify(practice['password_hash'], (directory/'owner-password').read_text())
        origin = practice['origin']
        migrations = json.loads((directory/'migrations.json').read_text())
        for name, service in SERVICES.items():
            config = configs[name]
            assert config['service'] == service and config['public_key'] == public
            assert config['dsn'].startswith('postgresql://'+name+'_runtime:')
            assert urlsplit(config['dsn']).hostname == primary(name)
            assert urlsplit(config['dsn']).path == '/'+name+'_db'
            assert config['amqp_url'].startswith('amqp://'+name+':')
            assert migrations[name]['dsn'].startswith('postgresql://'+name+'_migration:')
            assert migrations[name]['runtime_role'] == name+'_runtime'
            assert urlsplit(migrations[name]['dsn']).hostname == primary(name)
        assert len({(directory/f'pg-{name}-admin').read_text() for name in SERVICES}) == len(SERVICES)
        assert configs['learning']['redis_url'].startswith('redis://learning:')
        definitions = json.loads((directory/'rabbit-definitions.json').read_text())
        assert {u['name'] for u in definitions['users']} == set(SERVICES)
        for filename in ['operator.json', 'mcp.json', 'test-owner.json']:
            client = json.loads((directory/filename).read_text())
            assert client['base_url'] == origin
            for name, service in SERVICES.items():
                jwt.decode(client['tokens'][name], public, algorithms=['EdDSA'], audience=service, issuer='crucible')
        requested_origin = os.environ.get('CRUCIBLE_ORIGIN')
        if requested_origin and requested_origin != origin:
            raise ValueError('CRUCIBLE_ORIGIN отличается от существующей конфигурации')
    except Exception:
        raise ValueError('Конфигурация повреждена, несовместима или токены истекли; требуется явное обслуживание, файлы сохранены') from None


def generate(directory, owner):
    def write(name, value):
        path = directory/name
        path.write_text(json.dumps(value, indent=2) if isinstance(value, (dict, list)) else value)
        path.chmod(0o600 if name == "owner-password" else 0o644)
        if os.geteuid() == 0:
            os.chown(path, *owner)


    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


    def token(subject, audience, scopes):
        return jwt.encode({'iss': 'crucible', 'sub': subject, 'profile_id': 'owner', 'aud': audience,
                           'scopes': scopes, 'jti': str(uuid.uuid4()), 'exp': datetime.now(timezone.utc)+timedelta(days=30)}, private_pem, algorithm='EdDSA')


    owner_scopes = ['content:read', 'practice:read', 'practice:write', 'practice:help', 'review:append', 'correction:propose',
                    'correction:approve', 'question:resolve', 'learning:read', 'learning:write', 'reports:read', 'reports:write']
    agent_scopes = ['content:read', 'practice:read', 'practice:help', 'review:append', 'correction:propose', 'learning:read', 'reports:read', 'reports:write']
    services = {'content': 'content-service', 'practice': 'practice-service', 'learning': 'learning-service', 'reports': 'report-worker'}
    credentials = {n: {'runtime': secrets.token_hex(24), 'migration': secrets.token_hex(24), 'amqp': secrets.token_hex(24)} for n in services}
    password = secrets.token_urlsafe(18)
    write('owner-password', password)
    origin = os.environ.get('CRUCIBLE_ORIGIN', 'http://localhost:18080')
    migrations, configs = {}, {}
    for name, service in services.items():
        cred = credentials[name]
        write(f'pg-{name}-admin', secrets.token_hex(24))
        write(f'postgres-{name}-init.sql', init_sql(name, cred['runtime'], cred['migration']))
        migrations[name] = {'dsn': f'postgresql://{name}_migration:{cred["migration"]}@{primary(name)}:5432/{name}_db', 'runtime_role': name+'_runtime'}
        configs[name] = {'service': service, 'dsn': f'postgresql://{name}_runtime:{cred["runtime"]}@{primary(name)}:5432/{name}_db',
                         'public_key': public_pem, 'amqp_url': f'amqp://{name}:{cred["amqp"]}@rabbitmq:5672/study', 'downstreams': {}}
    configs['practice'].update(private_key=private_pem, password_hash=PasswordHasher().hash(password), origin=origin, owner_scopes=owner_scopes)
    configs['practice']['downstreams']['content'] = {'url': 'http://content:8000', 'token': token('practice-service', 'content-service', ['content:read', 'content:protected'])}
    redis_password = secrets.token_hex(24)
    configs['learning'].update(queue='learning.in', redis_url='redis://learning:'+redis_password+'@redis:6379/0')
    for name,scopes in {'practice':['practice:facts'],'content':['content:read']}.items():
        configs['learning']['downstreams'][name]={'url':f'http://{name}:8000','token':token('learning-service',services[name],scopes)}
    configs['reports']['queue'] = 'reports.in'
    for name, scopes in {'practice': ['practice:snapshot'], 'learning': ['learning:read']}.items():
        configs['reports']['downstreams'][name] = {'url': f'http://{name}:8000', 'token': token('report-worker', services[name], scopes)}
    write('redis.conf', 'bind 0.0.0.0\nprotected-mode yes\nsave ""\nmaxmemory 64mb\nmaxmemory-policy allkeys-lru\nuser default off\nuser learning on >'+redis_password+' ~learning:* +get +set +setex +del +ping\n')
    write('migrations.json', migrations)
    for name, c in configs.items():
        write(name+'.json', c)
    agent = {'base_url': origin, 'tokens': {n: token('study-agent', s, agent_scopes) for n, s in services.items()}}
    write('mcp.json', agent)
    write('operator.json', {'base_url': origin, 'tokens': {n: token('operator', s, owner_scopes+['content:publish', 'diagnostics:read']) for n, s in services.items()}})
    write('test-owner.json', {'base_url': origin, 'tokens': {n: token('test-owner', s, owner_scopes) for n, s in services.items()}})
    salt = secrets.token_bytes(4)
    users = []
    for name, cred in credentials.items():
        user_salt = secrets.token_bytes(4)
        users.append({'name': name, 'password_hash': base64.b64encode(user_salt+hashlib.sha256(user_salt+cred['amqp'].encode()).digest()).decode(), 'hashing_algorithm': 'rabbit_password_hashing_sha256', 'tags': []})
    bindings = [
        {'source': 'study.events', 'vhost': 'study', 'destination': 'learning.in', 'destination_type': 'queue', 'routing_key': route, 'arguments': {}}
        for route in ['practice.learning-facts.changed.v1', 'content.catalog.published.v1']]
    bindings += [{'source': 'study.events', 'vhost': 'study', 'destination': 'reports.in', 'destination_type': 'queue', 'routing_key': route, 'arguments': {}} for route in ['report.requested.v1', 'report.ready.v1', 'learning.progress.updated.v1']]
    queues = []
    for name in ['learning', 'reports']:
        queues += [{'name': name+'.in', 'vhost': 'study', 'durable': True, 'auto_delete': False,
                    'arguments': {'x-queue-type': 'quorum', 'x-dead-letter-exchange': 'study.dlx', 'x-dead-letter-routing-key': name+'.dlq'}},
                   {'name': name+'.dlq', 'vhost': 'study', 'durable': True, 'auto_delete': False, 'arguments': {'x-queue-type': 'quorum'}}]
        bindings.append({'source': 'study.dlx', 'vhost': 'study', 'destination': name+'.dlq', 'destination_type': 'queue', 'routing_key': name+'.dlq', 'arguments': {}})
    routes = {'content': '^content\\.catalog\\.published\\.v1$', 'practice': '^practice\\.learning-facts\\.changed\\.v1$',
              'learning': '^learning\\.progress\\.updated\\.v1$', 'reports': '^report\\.(requested|ready)\\.v1$'}
    definitions = {'users': users, 'vhosts': [{'name': 'study'}], 'permissions': [
        {'user': n, 'vhost': 'study', 'configure': '^$', 'write': '^study.events$', 'read': '^'+n+'\\.in$' if n in ['learning', 'reports'] else '^$'} for n in services],
        'topic_permissions': [{'user': n, 'vhost': 'study', 'exchange': 'study.events', 'write': route, 'read': '.*'} for n, route in routes.items()],
        'exchanges': [{'name': n, 'vhost': 'study', 'type': t, 'durable': True, 'auto_delete': False, 'internal': False, 'arguments': {}} for n, t in [('study.events', 'topic'), ('study.dlx', 'direct')]],
        'queues': queues, 'bindings': bindings}
    write('rabbit-definitions.json', definitions)


def setup(directory=Path('.secrets')):
    if directory.is_symlink():
        raise ValueError('Каталог секретов не должен быть symlink')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    owner = (directory.stat().st_uid, directory.stat().st_gid)
    with (directory/'.bootstrap.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        if os.geteuid() == 0:
            os.chown(lock.name, *owner)
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = [p for p in directory.iterdir() if p.name != '.bootstrap.lock']
        if entries:
            if (directory/'postgres-init.sql').exists() and not (directory/'postgres-content-init.sql').exists():
                raise ValueError('Обнаружена общая БД. Сначала выполните scripts/split-databases; секреты и данные сохранены')
            validate(directory)
            return 'existing'
        directory.chmod(0o700)
        # Validation completes before any final configuration file is installed.
        with tempfile.TemporaryDirectory(prefix='.bootstrap-', dir=directory) as temp:
            staged = Path(temp)
            generate(staged, owner)
            validate(staged)
            for name in sorted(REQUIRED):
                os.replace(staged/name, directory/name)
        return 'created'


if __name__ == '__main__':
    try:
        result = setup()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    print('Конфигурация проверена и сохранена.' if result == 'existing' else
          'Конфигурация создана. Пароль владельца: .secrets/owner-password (значение не выводится).')
