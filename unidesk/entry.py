"""Process entry point, shared by `python -m unidesk`, unidesk.pyw and the packaged exe."""
import os
import sys
from pathlib import Path


def run() -> int:
    # Without a console (pythonw / the packaged app) keep a log of warnings and QML errors.
    if sys.stderr is None or sys.stdout is None or getattr(sys, "frozen", False):
        log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "unidesk.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        os.environ.setdefault("QT_FORCE_STDERR_LOGGING", "1")

    if "--restore-taskbar" in sys.argv:
        # Used by the uninstaller (and handy if unidesk was killed): bring the Windows
        # taskbars back, and other apps' title bar and border colours.
        from unidesk import frames
        from unidesk.dock import winapi

        winapi.ghost_taskbar(False)
        frames.reset_all_windows()
        return 0

    from unidesk.app import main

    return main()
