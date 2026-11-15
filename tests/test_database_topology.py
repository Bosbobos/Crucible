"""Границы контейнеров, конфигурации и сетевой allowlist хранилищ."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from database_topology import OWNERS, database_host, primary, split_configuration
from firewall_namespace import DENIED, policy
import setup as bootstrap


def test_fresh_configuration_has_independent_admins_and_roles(tmp_path):
    root = tmp_path/'secrets'
    bootstrap.setup(root)
    admins = set()
    for owner in OWNERS:
        admins.add((root/f'pg-{owner}-admin').read_text())
        config = json.loads((root/(owner+'.json')).read_text())
        assert urlsplit(config['dsn']).hostname == primary(owner)
        sql = (root/f'postgres-{owner}-init.sql').read_text()
        assert f'CREATE DATABASE {owner}_db' in sql
        assert 'FROM PUBLIC' in sql
        assert all(f'CREATE ROLE {other}_' not in sql for other in OWNERS if other != owner)
    assert len(admins) == 4


def test_split_preserves_owner_password_tokens_and_runtime_credentials(tmp_path):
    root = tmp_path/'secrets'
    bootstrap.setup(root)
    configs = {owner: json.loads((root/(owner+'.json')).read_text()) for owner in OWNERS}
    for owner, config in configs.items():
        config['dsn'] = config['dsn'].replace(primary(owner), 'postgres')
        (root/(owner+'.json')).write_text(json.dumps(config))
    password = (root/'owner-password').read_bytes()
    tokens = (root/'operator.json').read_bytes()
    split_configuration(root)
    bootstrap.validate(root)
    assert (root/'owner-password').read_bytes() == password
    assert (root/'operator.json').read_bytes() == tokens
    for owner in OWNERS:
        current = json.loads((root/(owner+'.json')).read_text())
        assert urlsplit(current['dsn']).password == urlsplit(configs[owner]['dsn']).password


def test_compose_services_mount_only_own_storage_and_admin():
    config = yaml.safe_load(Path('compose.yaml').read_text())
    mounts = []
    for owner in OWNERS:
        database = config['services'][primary(owner)]
        assert database['networks'] == [owner+'_storage']
        assert not database.get('ports')
        mounts.extend(database['volumes'])
        assert database['secrets'][0]['source'] == 'pg_'+owner+'_admin'
        runtime = config['services'][owner]
        assert {n for n in runtime['networks'] if n.endswith('_storage')} == {owner+'_storage'}
        assert config['networks'][owner+'_storage']['internal'] is True
    assert len(set(mounts)) == 4
    assert not any(n.endswith('_storage') for n in config['services']['web']['networks'])


@pytest.mark.parametrize('owner', OWNERS)
def test_firewall_permits_only_own_database_and_replica(owner):
    names = ['web', *OWNERS, 'redis', 'rabbitmq', 'rabbitmq2', 'rabbitmq3']
    names += [primary(o)+suffix for o in OWNERS for suffix in ('', '-standby')]
    metadata = [{'Config': {'Labels': {'com.docker.compose.service': name, 'com.docker.compose.project': 'test'}},
                 'NetworkSettings': {'Networks': {'net': {'IPAddress': '10.0.0.'+str(i+2)}}}}
                for i, name in enumerate(names)]
    _, _, targets, rules = policy(metadata, owner)
    assert {name for name, port in targets if port == 5432} == {primary(owner), primary(owner)+'-standby'}
    assert {name for name, port in DENIED[owner] if port == 5432} == {primary(o) for o in OWNERS if o != owner}
    # Ограничение частоты касается только журнала; решения ACCEPT/REJECT без limit.
    assert rules[-1] == ['-j', 'REJECT']
    for index, rule in enumerate(rules):
        if 'limit' in rule:
            assert rule[rule.index('-j')+1] == 'NFLOG'
            assert rules[index+1][-1] in ('ACCEPT', 'REJECT')
            assert 'limit' not in rules[index+1]


def test_replicated_dsn_keeps_credentials_and_is_idempotent():
    dsn = 'postgresql://learning_runtime:secret@postgres:5432/learning_db'
    result = database_host(dsn, 'learning', replicated=True)
    assert result == 'postgresql://learning_runtime:secret@postgres-learning:5432,postgres-learning-standby:5432/learning_db?target_session_attrs=read-write&connect_timeout=2'
    assert database_host(result, 'learning', replicated=True) == result
