"""
AES-256-GCM field encryption.

Stored format: v1.<key_id>.<base64(nonce + ciphertext)>. The key id allows key
rotation without re-encrypting everything at once. `context` is authenticated
but not stored, so ciphertext copied to another row or organization won't decrypt.
"""

import base64
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

FORMAT_VERSION = "v1"
NONCE_BYTES = 12
KEY_BYTES = 32


class DecryptionError(Exception):
    pass


def _load_keys() -> dict[str, bytes]:
    keys = {}
    for entry in settings.FIELD_ENCRYPTION_KEYS:
        key_id, _, encoded = entry.partition(":")
        key = base64.b64decode(encoded)
        if not key_id or len(key) != KEY_BYTES:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS entries must be id:base64(32 bytes).")
        keys[key_id] = key
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain at least one key.")
    return keys


def encrypt(plaintext: bytes, context: str) -> str:
    keys = _load_keys()
    key_id = next(iter(keys))
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(keys[key_id]).encrypt(nonce, plaintext, context.encode())
    payload = base64.b64encode(nonce + ciphertext).decode()
    return f"{FORMAT_VERSION}.{key_id}.{payload}"


def decrypt(token: str, context: str) -> bytes:
    try:
        version, key_id, payload = token.split(".", 2)
        if version != FORMAT_VERSION:
            raise ValueError("Unsupported format version.")
        raw = base64.b64decode(payload)
        key = _load_keys()[key_id]
        return AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], context.encode())
    except (ValueError, KeyError, InvalidTag) as exc:
        raise DecryptionError("Could not decrypt value.") from exc


def blind_index(value: str, context: str) -> str:
    """A keyed fingerprint for duplicate checks. A plain hash could be brute-forced."""
    message = f"{context}:{value}".encode()
    return hmac.new(settings.BLIND_INDEX_KEY.encode(), message, hashlib.sha256).hexdigest()


def seal_file(content: bytes, context: str) -> bytes:
    """Binary form of `encrypt`, for files: <key_id length><key_id><nonce><ciphertext>."""
    keys = _load_keys()
    key_id = next(iter(keys))
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(keys[key_id]).encrypt(nonce, content, context.encode())
    encoded_id = key_id.encode()
    return bytes([len(encoded_id)]) + encoded_id + nonce + ciphertext


def open_file(sealed: bytes, context: str) -> bytes:
    try:
        id_end = 1 + sealed[0]
        key = _load_keys()[sealed[1:id_end].decode()]
        nonce = sealed[id_end : id_end + NONCE_BYTES]
        return AESGCM(key).decrypt(nonce, sealed[id_end + NONCE_BYTES :], context.encode())
    except (IndexError, KeyError, UnicodeDecodeError, InvalidTag) as exc:
        raise DecryptionError("Could not decrypt file.") from exc
