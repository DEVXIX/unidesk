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


def send_json(
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
    method: str = "POST",
    timeout: float = 12,
) -> tuple[int, object]:
    """A JSON request that carries a body, and hands back the status with it.

    The status comes back rather than raising, because the interesting answers
    here are the refusals: 401 means the token has expired and the widget should
    ask for the password again, and 422 carries the sentence explaining what was
    wrong with what was sent.
    """
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CONTEXT) as res:
            text = res.read().decode("utf-8", "replace")
            return res.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            return e.code, (json.loads(text) if text else None)
        except json.JSONDecodeError:
            return e.code, None
