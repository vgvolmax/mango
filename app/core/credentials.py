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
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(wintypes.BYTE))]


class WindowsDpapiBackend:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("DPAPI is available only on Windows")

        self._crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

        blob_pointer = ctypes.POINTER(_Blob)
        self._crypt32.CryptProtectData.argtypes = [
            blob_pointer,
            wintypes.LPCWSTR,
            blob_pointer,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_pointer,
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            blob_pointer,
            ctypes.POINTER(wintypes.LPWSTR),
            blob_pointer,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            blob_pointer,
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    @staticmethod
    def _blob(data: bytes) -> tuple[_Blob, object]:
        buffer = ctypes.create_string_buffer(data)
        return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))), buffer

    def _convert(self, data: bytes, operation: str) -> bytes:
        source, _input_buffer = self._blob(data)
        target = _Blob()
        function = getattr(self._crypt32, operation)
        if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            # Pass LocalFree the address returned by DPAPI as a pointer-sized value.
            self._kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))

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
