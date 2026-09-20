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


# The three shapes the menu offers, in the order they appear. The numbers in
# front are only there because Explorer lists subcommands alphabetically.
SHAPES = (("01one", "One pane", "1x1"),
          ("02two", "Two panes", "2x1"),
          ("03four", "Four panes", "2x2"))


def icon() -> str:
    """The picture Explorer puts beside the entry: unidesk's own.

    Frozen, the exe carries the icon in it and Explorer reads it from there.
    From a checkout, the interpreter's icon would be a Python logo, so the
    .ico beside the build is pointed at instead.
    """
    exe = Path(sys.executable)
    if exe.name.lower() in ("python.exe", "pythonw.exe"):
        own = Path(__file__).resolve().parent.parent / "build" / "unidesk.ico"
        if own.exists():
            return str(own)
    return str(exe)


def launcher(shape: str = "1x1") -> str:
    """The command line that opens a terminal, however unidesk is installed."""
    exe = Path(sys.executable)
    if exe.name.lower() in ("python.exe", "pythonw.exe"):
        # Running from a checkout. The entry script by full path, not
        # `-m unidesk`, because Explorer will not be standing in the project
        # directory when it runs this.
        script = Path(__file__).resolve().parent.parent / "unidesk.pyw"
        return f'"{exe.with_name("pythonw.exe")}" "{script}" --new-terminal {shape}'
    return f'"{exe}" --new-terminal {shape}'


def installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY):
            return True
    except OSError:
        return False


def install():
    """Put the entry in the desktop's menu, pointing at this copy.

    A cascading one: the parent says nothing on its own, and the three sizes
    hang off it. That is what SubCommands means to Explorer - an empty value
    tells it to look for a `shell` key underneath and build a submenu from
    whatever it finds, in alphabetical order.
    """
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, LABEL)
        winreg.SetValueEx(key, "SubCommands", 0, winreg.REG_SZ, "")
        # The icon Explorer shows beside it, taken from the running program.
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon())
    for folder, label, shape in SHAPES:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{KEY}\shell\{folder}") as entry:
            winreg.SetValueEx(entry, "MUIVerb", 0, winreg.REG_SZ, label)
            winreg.SetValueEx(entry, "Icon", 0, winreg.REG_SZ, icon())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{KEY}\shell\{folder}\command") as command:
            winreg.SetValueEx(command, None, 0, winreg.REG_SZ, launcher(shape))


def remove():
    # Deepest first: a key with anything under it cannot be deleted.
    paths = []
    for folder, _, _ in SHAPES:
        paths += [rf"{KEY}\shell\{folder}\command", rf"{KEY}\shell\{folder}"]
    paths += [KEY + r"\shell", KEY + r"\command", KEY]
    for path in paths:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


# Windows 11 shows a menu of its own on a right-click, and only lists things
# from packaged shell extensions in it - everything registered the way this is
# (and 7-Zip, and git, and Notepad++) goes under "Show more options". The only
# switch that changes that is this one: an empty override for the CLSID of the
# new menu, which turns it off and brings back the full Windows 10 one. It is
# the tweak everybody uses for this, it applies to every right-click and not
# just ours, and it is undone by deleting the same key.
CLASSIC = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"


def classic_menu() -> bool:
    """Whether Windows is showing the old, complete right-click menu."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLASSIC):
            return True
    except OSError:
        return False


def set_classic_menu(on: bool) -> bool:
    """Turn the old menu on or off. Explorer has to be restarted to notice,
    which this does - it takes a second and open File Explorer windows close."""
    if on == classic_menu():
        return False
    if on:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLASSIC) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "")
    else:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, CLASSIC)
        except OSError:
            pass
    restart_explorer()
    return True


def restart_explorer():
    """Explorer reads the context menu setting once, at startup."""
    import subprocess

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], creationflags=flags,
                   capture_output=True)
    subprocess.Popen(["explorer.exe"], creationflags=flags, close_fds=True)


def apply(wanted: bool):
    """Make the registry match the setting, and say whether anything changed."""
    if wanted == installed():
        return False
    install() if wanted else remove()
    return True
