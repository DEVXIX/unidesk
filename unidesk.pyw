"""Launcher without a console: double-click, startup entry, and the packaged exe's entry script."""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from unidesk.entry import run

sys.exit(run())
