"""DPAPI-protected credential persistence (with injectable test backend)."""

from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Protocol


class ProtectionBackend(Protocol):
    def protect(self, data: bytes) -> bytes: ...
    def unprotect(self, data: bytes) -> bytes: ...


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDpapiBackend:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("DPAPI is available only on Windows")

    @staticmethod
    def _blob(data: bytes) -> tuple[_Blob, object]:
        buffer = ctypes.create_string_buffer(data)
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def _convert(self, data: bytes, operation: str) -> bytes:
        source, buffer = self._blob(data)
        target = _Blob()
        function = getattr(ctypes.windll.crypt32, operation)
        if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            local_free = ctypes.windll.kernel32.LocalFree
            local_free.argtypes = [ctypes.c_void_p]
            local_free.restype = ctypes.c_void_p
            local_free(target.pbData)

    def protect(self, data: bytes) -> bytes:
        return self._convert(data, "CryptProtectData")

    def unprotect(self, data: bytes) -> bytes:
        return self._convert(data, "CryptUnprotectData")


class CredentialsStore:
    def __init__(self, path: Path, backend: ProtectionBackend | None = None) -> None:
        self.path = path
        self.backend = backend

    def _backend(self) -> ProtectionBackend:
        return self.backend or WindowsDpapiBackend()

    def save(self, api_key: str, api_salt: str) -> None:
        plain = json.dumps({"api_key": api_key, "api_salt": api_salt}).encode("utf-8")
        protected = self._backend().protect(plain)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_bytes(protected)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def load(self) -> tuple[str, str] | None:
        try:
            value = json.loads(self._backend().unprotect(self.path.read_bytes()).decode("utf-8"))
            return str(value["api_key"]), str(value["api_salt"])
        except (OSError, ValueError, KeyError, UnicodeError):
            return None

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
