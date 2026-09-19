"""Which camera to send.

OpenCV opens a camera by number and has no idea what any of them are called,
so a picker built on it alone offers "0" and "1" and leaves you guessing.
Windows knows the names, so the two are put together: the indices come from
opening cameras until they stop answering, and the names from the device list.
When the counts agree - which is the ordinary case - the n-th name belongs to
the n-th camera.

They can disagree: a camera that is plugged in but already in use by something
else is on Windows' list and will not open. Then the numbers stand on their
own, which is worse to read but still lets somebody pick the other camera.

The list is cached, because finding it means opening every camera in turn and
that costs about half a second each.
"""
from __future__ import annotations

import subprocess

MAX_PROBE = 5

_cache: list[dict] | None = None


def _windows_names() -> list[str]:
    """What Windows calls the cameras attached to this machine."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq 'Camera' } |"
                " Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _openable() -> list[int]:
    """The camera numbers that actually answer."""
    found: list[int] = []
    try:
        import cv2
    except ImportError:
        return found
    for index in range(MAX_PROBE):
        capture = None
        try:
            # DirectShow, the same backend the call captures with - so a camera
            # that opens here is one that will open there.
            capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if capture.isOpened():
                found.append(index)
        except Exception:
            pass
        finally:
            if capture is not None:
                capture.release()
    return found


def cameras(refresh: bool = False) -> list[dict]:
    """Every camera, as {id, name}; the id is the number OpenCV opens."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    indices = _openable()
    names = _windows_names()
    if len(names) == len(indices):
        _cache = [{"id": str(i), "name": name} for i, name in zip(indices, names)]
    else:
        _cache = [{"id": str(i), "name": f"Camera {i}"} for i in indices]
    return _cache
