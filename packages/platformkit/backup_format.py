"""Версионированный зашифрованный контейнер резервных копий Crucible."""
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'CRUCIBLEBACKUP1'
ASSOCIATED_DATA = b'Crucible backup v1'
SUFFIX = '.cruciblebackup'


def encrypt_backup(archive, key):
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, archive, ASSOCIATED_DATA)


def decrypt_backup(raw, key):
    offset = len(MAGIC)
    if not raw.startswith(MAGIC) or len(raw) < offset + 12 + 16:
        raise ValueError('Неизвестный или неполный формат резервной копии')
    return AESGCM(key).decrypt(raw[offset:offset + 12], raw[offset + 12:], ASSOCIATED_DATA)
