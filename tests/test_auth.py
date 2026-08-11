import hashlib

from app.mango.auth import make_signature


def test_signature_is_deterministic():
    expected = hashlib.sha256(b"key{\"value\":1}salt").hexdigest()
    assert make_signature("key", '{"value":1}', "salt") == expected
