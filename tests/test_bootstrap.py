"""Проверки сохранности секретов и отказа от неполной конфигурации."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('bootstrap', Path('scripts/setup.py'))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def checksums(root):
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in bootstrap.REQUIRED}


def test_bootstrap_reuses_credentials_and_rejects_partial_state(tmp_path):
    root = tmp_path/'secrets'
    assert bootstrap.setup(root) == 'created'
    before = checksums(root)
    assert bootstrap.setup(root) == 'existing'
    assert checksums(root) == before
    (root/'learning.json').unlink()
    with pytest.raises(ValueError, match='Неполная конфигурация'):
        bootstrap.setup(root)
    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
               for name, digest in before.items() if name != 'learning.json')
    assert not (root/'learning.json').exists()


def test_bootstrap_rejects_mismatched_password_without_repair(tmp_path):
    root = tmp_path/'secrets'
    bootstrap.setup(root)
    (root/'owner-password').write_text('incorrect-password')
    before = checksums(root)
    with pytest.raises(ValueError, match='Конфигурация повреждена'):
        bootstrap.setup(root)
    assert checksums(root) == before


def test_fresh_character_tokens_have_scoped_permissions_and_stable_reuse(tmp_path):
    import json,jwt
    root=tmp_path/'secrets';bootstrap.setup(root)
    public=json.loads((root/'practice.json').read_text())['public_key']
    for filename,expected in [('operator.json',{'character:read','character:write','character:snapshot'}),
        ('test-owner.json',{'character:read','character:write'}),('mcp.json',{'character:read'})]:
        token=json.loads((root/filename).read_text())['tokens']['character']
        claims=jwt.decode(token,public,algorithms=['EdDSA'],audience='character-service',issuer='crucible')
        assert expected<=set(claims['scopes'])
        if filename=='mcp.json':assert 'character:write' not in claims['scopes']
    before=checksums(root);bootstrap.setup(root);assert checksums(root)==before
