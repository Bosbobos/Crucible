"""Имена независимых хранилищ и генерация конфигурации без смены runtime-паролей."""
import json
import secrets
from urllib.parse import urlsplit, urlunsplit

OWNERS = ('content', 'practice', 'learning', 'reports', 'character')


def primary(owner):
    return 'postgres-' + owner


def standby(owner):
    return primary(owner) + '-standby'


def database_host(dsn, owner, *, replicated=False):
    parsed = urlsplit(dsn)
    credentials = parsed.netloc.rsplit('@', 1)[0]
    hosts = primary(owner) + ':5432'
    if replicated:
        hosts += ',' + standby(owner) + ':5432'
    return urlunsplit((parsed.scheme, credentials + '@' + hosts, parsed.path,
                      'target_session_attrs=read-write&connect_timeout=2' if replicated else '', ''))


def init_sql(owner, runtime_password, migration_password):
    # Пароли приходят из генератора или существующего DSN, а не из SQL пользователя.
    def literal(value):
        return "'" + value.replace("'", "''") + "'"
    return '\n'.join([
        'REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;',
        'REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;',
        f'CREATE ROLE {owner}_migration LOGIN PASSWORD {literal(migration_password)} NOSUPERUSER NOCREATEDB NOCREATEROLE;',
        f'CREATE ROLE {owner}_runtime LOGIN PASSWORD {literal(runtime_password)} NOSUPERUSER NOCREATEDB NOCREATEROLE;',
        f'CREATE DATABASE {owner}_db OWNER {owner}_migration;',
        f'REVOKE ALL ON DATABASE {owner}_db FROM PUBLIC;',
        f'GRANT CONNECT ON DATABASE {owner}_db TO {owner}_runtime;',
        f'\\connect {owner}_db',
        'REVOKE CREATE ON SCHEMA public FROM PUBLIC;',
        f'GRANT USAGE ON SCHEMA public TO {owner}_runtime;',
        '\\connect postgres', '',
    ])


def split_configuration(directory):
    """Подготавливает новую топологию в приватной копии старой конфигурации."""
    from urllib.parse import unquote
    migrations = json.loads((directory / 'migrations.json').read_text())
    for owner in OWNERS:
        path = directory / (owner + '.json')
        config = json.loads(path.read_text())
        sql = init_sql(owner, unquote(urlsplit(config['dsn']).password),
                       unquote(urlsplit(migrations[owner]['dsn']).password))
        (directory / f'postgres-{owner}-init.sql').write_text(sql)
        (directory / f'pg-{owner}-admin').write_text(secrets.token_hex(24))
        config['dsn'] = database_host(config['dsn'], owner)
        migrations[owner]['dsn'] = database_host(migrations[owner]['dsn'], owner)
        path.write_text(json.dumps(config, indent=2))
    (directory / 'migrations.json').write_text(json.dumps(migrations, indent=2))
