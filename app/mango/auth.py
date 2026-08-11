"""MANGO request signing."""

import hashlib


def make_signature(api_key: str, json_text: str, api_salt: str) -> str:
    return hashlib.sha256(f"{api_key}{json_text}{api_salt}".encode("utf-8")).hexdigest()
