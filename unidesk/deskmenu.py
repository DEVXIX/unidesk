""""New terminal" on the desktop's own right-click menu.

The desk window is clipped to its widgets, so a right-click on empty desktop
never reaches unidesk - it reaches Explorer. The only way into that menu is
Explorer's own: a verb under Directory\\Background\\shell, which runs a command.

Worth knowing before looking for it: on Windows 11 the menu that opens on a
right-click is a new one, and it only lists entries from packaged shell
extensions. Everything registered the old way - this, 7-Zip, Notepad++, git -
is one level down, under "Show more options" (or Shift+right-click, or the
menu key). That is a Windows decision, not something this can route around
without shipping a signed package.

It is off unless asked for, and it only ever writes under HKCU.
"""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

KEY = r"Software\Classes\Directory\Background\shell\unidesk.terminal"
LABEL = "New terminal (unidesk)"


def launcher() -> str:
    """The command line that opens a terminal, however unidesk is installed."""
    exe = Path(sys.executable)
    if exe.name.lower() in ("python.exe", "pythonw.exe"):
        # Running from a checkout. The entry script by full path, not
        # `-m unidesk`, because Explorer will not be standing in the project
        # directory when it runs this.
        script = Path(__file__).resolve().parent.parent / "unidesk.pyw"
        return f'"{exe.with_name("pythonw.exe")}" "{script}" --new-terminal'
    return f'"{exe}" --new-terminal'


def installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY):
            return True
    except OSError:
        return False


def install():
    """Put the entry in the desktop's menu, pointing at this copy."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, LABEL)
        # The icon Explorer shows beside it, taken from the running program.
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, str(Path(sys.executable)))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY + r"\command") as command:
        winreg.SetValueEx(command, None, 0, winreg.REG_SZ, launcher())


def remove():
    for path in (KEY + r"\command", KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


def apply(wanted: bool):
    """Make the registry match the setting, and say whether anything changed."""
    if wanted == installed():
        return False
    install() if wanted else remove()
    return True
