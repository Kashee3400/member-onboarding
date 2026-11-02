import base64

import pytest

from apps.core import crypto

KEY_1 = "k1:" + base64.b64encode(b"1" * 32).decode()
KEY_2 = "k2:" + base64.b64encode(b"2" * 32).decode()


def test_round_trip(settings):
    settings.FIELD_ENCRYPTION_KEYS = [KEY_1]
    assert crypto.decrypt(crypto.encrypt(b"value", "ctx"), "ctx") == b"value"


def test_the_same_value_encrypts_differently_each_time(settings):
    settings.FIELD_ENCRYPTION_KEYS = [KEY_1]
    assert crypto.encrypt(b"value", "ctx") != crypto.encrypt(b"value", "ctx")


def test_old_values_stay_readable_after_key_rotation(settings):
    settings.FIELD_ENCRYPTION_KEYS = [KEY_1]
    old = crypto.encrypt(b"value", "ctx")

    settings.FIELD_ENCRYPTION_KEYS = [KEY_2, KEY_1]

    assert crypto.decrypt(old, "ctx") == b"value"
    assert crypto.encrypt(b"value", "ctx").startswith("v1.k2.")


@pytest.mark.parametrize("token", ["garbage", "v1.k1.!!!", "v2.k1.AAAA", "v1.missing.AAAA"])
def test_malformed_values_fail_cleanly(settings, token):
    settings.FIELD_ENCRYPTION_KEYS = [KEY_1]
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(token, "ctx")


def test_tampered_ciphertext_is_rejected(settings):
    settings.FIELD_ENCRYPTION_KEYS = [KEY_1]
    token = crypto.encrypt(b"value", "ctx")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(tampered, "ctx")
