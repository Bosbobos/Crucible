"""Перенос имени не должен повреждать резервные копии."""
import pytest
from cryptography.exceptions import InvalidTag
from platformkit.backup_format import encrypt_backup, decrypt_backup


def test_encrypted_archive_round_trip_and_authentication():
    key = bytes(range(32))
    archive = b'coordinated archive\x00\xff'
    raw = encrypt_backup(archive, key)
    assert decrypt_backup(raw, key) == archive
    assert encrypt_backup(archive, key) != raw
    with pytest.raises(InvalidTag):
        decrypt_backup(raw[:-1] + bytes([raw[-1] ^ 1]), key)
    with pytest.raises(InvalidTag):
        decrypt_backup(raw, bytes(reversed(key)))


@pytest.mark.parametrize('raw', [b'', b'unknown archive', b'CRUCIBLEBACKUP1' + b'\x00' * 20])
def test_incomplete_or_unknown_backup_is_rejected(raw):
    with pytest.raises(ValueError):
        decrypt_backup(raw, bytes(range(32)))
