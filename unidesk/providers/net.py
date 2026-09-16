"""Tiny HTTP helpers (stdlib only) for provider threads."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

try:
    # Verify certificates with Windows' own verifier: it knows new roots (e.g.
    # Let's Encrypt YE1 chains) that Python's bundled logic reports as expired.
    import truststore

    _CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    _CONTEXT = ssl.create_default_context()

USER_AGENT = "unidesk/0.1 (desktop widgets)"


def get_text(url: str, headers: dict | None = None, timeout: float = 12) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CONTEXT) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def get_json(url: str, headers: dict | None = None, timeout: float = 12):
    status, text = get_text(url, {"Accept": "application/json", **(headers or {})}, timeout)
    if status == 404:
        return None
    if status >= 400 or not text:
        raise RuntimeError(f"{url.split('?')[0]} -> HTTP {status}")
    return json.loads(text)
