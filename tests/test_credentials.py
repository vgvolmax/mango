from app.core.credentials import CredentialsStore


class ReverseBackend:
    def protect(self, data): return data[::-1]
    def unprotect(self, data): return data[::-1]


def test_credentials_roundtrip_and_delete(tmp_path):
    store = CredentialsStore(tmp_path / "credentials.dat", ReverseBackend())
    store.save("key", "secret")
    assert b"secret" not in store.path.read_bytes()
    assert store.load() == ("key", "secret")
    store.delete()
    assert store.load() is None
