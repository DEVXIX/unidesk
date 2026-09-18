"""Apps that can be themed from outside get unidesk's colours too, live:

- VS Code (and Insiders, Cursor, VSCodium, Windsurf): its colour customisations
  for the title bar, menus, activity and side bars, tabs, status bar, scroll
  bars and popups. The editor itself keeps your colour theme.
- Windows Terminal: a "unidesk" theme for the title bar / tab row and the window
  frame. The terminal's own colour scheme stays yours.

- Classic apps (menus, menu bars, scroll bars, status bars, toolbars): through
  the unidesk Windhawk mod in windhawk/, which reads the palette published under
  HKCU\\Software\\unidesk\\Palette.

Both apps pick changes up as soon as their settings file is saved. Only those
settings are written, the rest of each file (comments too) is left as it is,
and what was there before is kept in %LOCALAPPDATA%\\unidesk\\app-themes.json
and put back when the option is turned off."""
from __future__ import annotations

import json
import os
import re
import winreg
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Slot

STATE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "unidesk" / "app-themes.json"
VSCODE_KEY = "workbench.colorCustomizations"
TERMINAL_THEME = "unidesk"
_LITERAL = re.compile(r"[^\s,}\]/]+")


# ---- JSON with comments, edited in place ---------------------------------------------

def _skip_space(text: str, i: int) -> int:
    """Past whitespace and // or /* */ comments."""
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n﻿":
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end + 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            break
    return i


def _skip_string(text: str, i: int) -> int:
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == '"':
            return i + 1
        else:
            i += 1
    raise ValueError("unterminated string")


def _skip_value(text: str, i: int) -> int:
    if i >= len(text):
        raise ValueError("missing value")
    if text[i] == '"':
        return _skip_string(text, i)
    if text[i] in "{[":
        depth = 0
        while i < len(text):
            i = _skip_space(text, i)
            if i >= len(text):
                break
            if text[i] == '"':
                i = _skip_string(text, i)
                continue
            if text[i] in "{[":
                depth += 1
            elif text[i] in "}]":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        raise ValueError("unbalanced brackets")
    match = _LITERAL.match(text, i)
    if not match:
        raise ValueError(f"unexpected {text[i]!r} at {i}")
    return match.end()


def _members(text: str):
    """The top-level object -> (index of "{", [(key, key start, value start, value end)], index of "}")."""
    opening = _skip_space(text, 0)
    if opening >= len(text) or text[opening] != "{":
        raise ValueError("not a JSON object")
    i, members = opening + 1, []
    while True:
        i = _skip_space(text, i)
        if i >= len(text):
            raise ValueError("unclosed object")
        if text[i] == "}":
            return opening, members, i
        if text[i] == ",":
            i += 1
            continue
        if text[i] != '"':
            raise ValueError(f"expected a key at {i}")
        key_start = i
        i = _skip_string(text, i)
        key = json.loads(text[key_start:i])
        i = _skip_space(text, i)
        if i >= len(text) or text[i] != ":":
            raise ValueError(f"expected ':' at {i}")
        value_start = _skip_space(text, i + 1)
        value_end = _skip_value(text, value_start)
        members.append((key, key_start, value_start, value_end))
        i = value_end


def loads(text: str):
    """JSON that may have comments and trailing commas."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == '"':
            end = _skip_string(text, i)
            out.append(text[i:end])
            i = end
        elif text.startswith(("//", "/*"), i):
            out.append(" ")
            i = _skip_space(text, i)
        elif text[i] == ",":
            nxt = _skip_space(text, i + 1)
            if nxt >= n or text[nxt] not in "}]":
                out.append(",")
            i += 1
        else:
            out.append(text[i])
            i += 1
    return json.loads("".join(out).strip().lstrip("﻿") or "{}")


def _indent(text: str, index: int) -> str:
    line = text[text.rfind("\n", 0, index) + 1:]
    return re.match(r"[ \t]*", line).group(0)


def _dump(value, indent: str) -> str:
    return json.dumps(value, indent=4, ensure_ascii=False).replace("\n", "\n" + indent)


def set_member(text: str, key: str, value) -> str:
    """Set one top-level key; everything else in the file stays byte for byte."""
    if not text.strip():
        return json.dumps({key: value}, indent=4, ensure_ascii=False) + "\n"
    opening, members, closing = _members(text)
    for name, key_start, value_start, value_end in members:
        if name == key:
            return text[:value_start] + _dump(value, _indent(text, key_start)) + text[value_end:]
    if not members:
        return text[:opening + 1] + "\n    " + json.dumps(key) + ": " + _dump(value, "    ") + "\n" + text[closing:]
    _, last_key, _, last_end = members[-1]
    indent = _indent(text, last_key)
    after = _skip_space(text, last_end)
    at, comma = (after + 1, "") if after < len(text) and text[after] == "," else (last_end, ",")
    return text[:at] + comma + "\n" + indent + json.dumps(key) + ": " + _dump(value, indent) + text[at:]


def remove_member(text: str, key: str) -> str:
    opening, members, closing = _members(text)
    for index, (name, key_start, _value_start, value_end) in enumerate(members):
        if name != key:
            continue
        if index > 0:  # take the comma before it along
            return text[:members[index - 1][3]] + text[value_end:]
        if len(members) > 1:  # the first of several: up to the next key's line
            next_key = members[1][1]
            return text[:text.rfind("\n", 0, key_start) + 1] + text[text.rfind("\n", 0, next_key) + 1:]
        return text[:opening + 1] + "\n" + text[closing:]
    return text


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def _write(path: Path, text: str):
    temp = path.with_name(path.name + ".unidesk-tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


# ---- where the apps keep their settings ------------------------------------------------

def vscode_settings() -> list[Path]:
    roaming = Path(os.environ.get("APPDATA", ""))
    return [roaming / app / "User" / "settings.json"
            for app in ("Code", "Code - Insiders", "Cursor", "VSCodium", "Windsurf") if (roaming / app / "User").is_dir()]


def terminal_settings() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [local / "Packages" / f"{package}_8wekyb3d8bbwe" / "LocalState" / "settings.json"
                  for package in ("Microsoft.WindowsTerminal", "Microsoft.WindowsTerminalPreview")]
    candidates.append(local / "Microsoft" / "Windows Terminal" / "settings.json")  # unpackaged installs
    return [p for p in candidates if p.is_file()]


# ---- colours ----------------------------------------------------------------------------

def vscode_colors(c: dict) -> dict[str, str]:
    """Material You roles -> VS Code colour ids (the editor keeps your theme)."""
    def alpha(role: str, amount: int) -> str:
        return f"{c[role]}{amount:02x}"

    return {
        "titleBar.activeBackground": c["surfaceContainer"],
        "titleBar.activeForeground": c["onSurface"],
        "titleBar.inactiveBackground": c["surface"],
        "titleBar.inactiveForeground": c["onSurfaceVariant"],
        "titleBar.border": c["surfaceContainer"],
        "commandCenter.background": c["surfaceContainerHighest"],
        "commandCenter.foreground": c["onSurfaceVariant"],
        "commandCenter.activeBackground": c["surfaceBright"],
        "commandCenter.border": alpha("outlineVariant", 0x80),
        "menubar.selectionBackground": c["secondaryContainer"],
        "menubar.selectionForeground": c["onSecondaryContainer"],
        "menu.background": c["surfaceContainerHigh"],
        "menu.foreground": c["onSurface"],
        "menu.selectionBackground": c["secondaryContainer"],
        "menu.selectionForeground": c["onSecondaryContainer"],
        "menu.separatorBackground": c["outlineVariant"],
        "menu.border": c["outlineVariant"],
        "activityBar.background": c["surfaceContainer"],
        "activityBar.foreground": c["primary"],
        "activityBar.inactiveForeground": c["onSurfaceVariant"],
        "activityBar.activeBorder": c["primary"],
        "activityBar.border": c["surfaceContainer"],
        "activityBarBadge.background": c["primary"],
        "activityBarBadge.foreground": c["onPrimary"],
        "sideBar.background": c["surfaceContainerLow"],
        "sideBar.foreground": c["onSurface"],
        "sideBar.border": c["surfaceContainerLow"],
        "sideBarTitle.foreground": c["onSurfaceVariant"],
        "sideBarSectionHeader.background": c["surfaceContainerLow"],
        "sideBarSectionHeader.foreground": c["onSurface"],
        "sideBarSectionHeader.border": c["surfaceContainerLow"],
        "editorGroupHeader.tabsBackground": c["surfaceContainer"],
        "editorGroupHeader.tabsBorder": c["surfaceContainer"],
        "tab.inactiveBackground": c["surfaceContainer"],
        "tab.inactiveForeground": c["onSurfaceVariant"],
        "tab.activeForeground": c["onSurface"],
        "tab.activeBorderTop": c["primary"],
        "tab.border": c["surfaceContainer"],
        "statusBar.background": c["surfaceContainer"],
        "statusBar.foreground": c["onSurfaceVariant"],
        "statusBar.border": c["surfaceContainer"],
        "statusBar.noFolderBackground": c["surfaceContainer"],
        "statusBar.debuggingBackground": c["tertiaryContainer"],
        "statusBar.debuggingForeground": c["onTertiaryContainer"],
        "statusBarItem.hoverBackground": alpha("onSurface", 0x1F),
        "statusBarItem.remoteBackground": c["primary"],
        "statusBarItem.remoteForeground": c["onPrimary"],
        "scrollbar.shadow": "#00000000",
        "scrollbarSlider.background": alpha("onSurfaceVariant", 0x33),
        "scrollbarSlider.hoverBackground": alpha("onSurfaceVariant", 0x55),
        "scrollbarSlider.activeBackground": alpha("primary", 0x99),
        "quickInput.background": c["surfaceContainerHigh"],
        "quickInput.foreground": c["onSurface"],
        "quickInputList.focusBackground": c["secondaryContainer"],
        "quickInputList.focusForeground": c["onSecondaryContainer"],
        "editorWidget.background": c["surfaceContainerHigh"],
        "notifications.background": c["surfaceContainerHigh"],
        "notificationCenterHeader.background": c["surfaceContainerHighest"],
        "list.activeSelectionBackground": c["secondaryContainer"],
        "list.activeSelectionForeground": c["onSecondaryContainer"],
        "list.inactiveSelectionBackground": c["surfaceContainerHighest"],
        "list.hoverBackground": alpha("onSurface", 0x14),
        "list.highlightForeground": c["primary"],
        "input.background": c["surfaceContainerHighest"],
        "input.border": alpha("outlineVariant", 0x80),
        "dropdown.background": c["surfaceContainerHigh"],
        "panel.border": c["outlineVariant"],
        "panelTitle.activeBorder": c["primary"],
        "panelTitle.activeForeground": c["onSurface"],
        "focusBorder": alpha("primary", 0x99),
        "progressBar.background": c["primary"],
        "badge.background": c["primaryContainer"],
        "badge.foreground": c["onPrimaryContainer"],
        "button.background": c["primary"],
        "button.foreground": c["onPrimary"],
        "button.hoverBackground": alpha("primary", 0xD9),
        "textLink.foreground": c["primary"],
        "sash.hoverBorder": c["primary"],
    }


def terminal_theme(c: dict, dark: bool) -> dict:
    return {
        "name": TERMINAL_THEME,
        "window": {"applicationTheme": "dark" if dark else "light", "useMica": False,
                   "frame": c["primary"], "unfocusedFrame": c["outlineVariant"]},
        "tabRow": {"background": c["surfaceContainer"] + "ff", "unfocusedBackground": c["surface"] + "ff"},
        "tab": {"background": c["surfaceContainerHighest"] + "ff", "unfocusedBackground": c["surfaceContainer"] + "ff"},
    }


# ---- the palette for the Windhawk mod -------------------------------------------------------

PALETTE_KEY = r"Software\unidesk\Palette"
PALETTE_ROLES = ("surfaceContainerLow", "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest", "onSurface",
                 "onSurfaceVariant", "outline", "outlineVariant", "primary", "secondaryContainer", "onSecondaryContainer",
                 "primaryContainer", "onPrimaryContainer")


def _colorref(hex_color: str) -> int:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16) | int(value[2:4], 16) << 8 | int(value[4:6], 16) << 16


def publish_palette(palette: dict | None, dark: bool = True):
    """Colours as COLORREF DWORDs, then Version bumped last so the mod reads a
    complete set. None switches the mod off (apps go back to their own look)."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PALETTE_KEY) as key:
        if palette is not None:
            for role in PALETTE_ROLES:
                winreg.SetValueEx(key, role, 0, winreg.REG_DWORD, _colorref(palette[role]))
            winreg.SetValueEx(key, "Dark", 0, winreg.REG_DWORD, int(bool(dark)))
        winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, int(palette is not None))
        try:
            version = int(winreg.QueryValueEx(key, "Version")[0])
        except OSError:
            version = 0
        winreg.SetValueEx(key, "Version", 0, winreg.REG_DWORD, (version + 1) & 0x7FFFFFFF or 1)


# ---- applying and putting back ------------------------------------------------------------

def apply_vscode(path: Path, colors: dict, record: dict) -> bool:
    """Set our colour ids, remembering in `record` what each was before. True if the file changed."""
    text = _read(path)
    doc = loads(text) if text.strip() else {}
    current = doc.get(VSCODE_KEY)
    if current is not None and not isinstance(current, dict):
        return False  # something unexpected there: leave it alone
    record.setdefault("existed", VSCODE_KEY in doc)
    before = record.setdefault("before", {})
    merged = dict(current or {})
    for name, value in colors.items():
        if name not in before:
            before[name] = merged.get(name)  # None: it wasn't set
        merged[name] = value
    if merged == current:
        return False
    _write(path, set_member(text, VSCODE_KEY, merged))
    return True


def restore_vscode(path: Path, record: dict):
    text = _read(path)
    if not text.strip():
        return
    current = loads(text).get(VSCODE_KEY)
    if not isinstance(current, dict):
        return
    merged = dict(current)
    for name, value in record.get("before", {}).items():
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = value
    if not merged and not record.get("existed"):
        _write(path, remove_member(text, VSCODE_KEY))
    elif merged != current:
        _write(path, set_member(text, VSCODE_KEY, merged))


def apply_terminal(path: Path, theme: dict, record: dict) -> bool:
    text = original = _read(path)
    doc = loads(text)
    themes = doc.get("themes", [])
    if not isinstance(themes, list):
        return False
    # Already ours (e.g. the saved state was lost): what comes back is Terminal's default.
    ours = doc.get("theme") == TERMINAL_THEME
    record.setdefault("had_theme", "theme" in doc and not ours)
    record.setdefault("theme", None if ours else doc.get("theme"))
    record.setdefault("had_themes", "themes" in doc)
    updated = [t for t in themes if not (isinstance(t, dict) and t.get("name") == TERMINAL_THEME)] + [theme]
    if updated != themes:
        text = set_member(text, "themes", updated)
    if doc.get("theme") != TERMINAL_THEME:
        text = set_member(text, "theme", TERMINAL_THEME)
    if text == original:
        return False
    _write(path, text)
    return True


def restore_terminal(path: Path, record: dict):
    text = original = _read(path)
    if not text.strip():
        return
    doc = loads(text)
    themes = doc.get("themes")
    if isinstance(themes, list):
        kept = [t for t in themes if not (isinstance(t, dict) and t.get("name") == TERMINAL_THEME)]
        if kept != themes:
            text = set_member(text, "themes", kept) if kept or record.get("had_themes") else remove_member(text, "themes")
    if loads(text).get("theme") == TERMINAL_THEME:  # unless you've picked another theme since
        text = set_member(text, "theme", record.get("theme")) if record.get("had_theme") else remove_member(text, "theme")
    if text != original:
        _write(path, text)


class AppThemes(QObject):
    """style.app_themes: true themes VS Code and Windows Terminal with unidesk's
    colours, following every palette change."""

    def __init__(self, store, theme):
        super().__init__()
        self._store, self._theme = store, theme
        self._enabled = False
        self._state: dict[str, dict] = self._load_state()  # settings file -> what it had before
        self._last: dict[str, object] = {}                  # settings file -> what we last wrote there
        # The palette changes with every song; write once it has settled.
        self._soon = QTimer(self, singleShot=True, interval=2000, timeout=self.apply)
        store.changed.connect(self.configure)
        theme.colorsChanged.connect(lambda: self._enabled and self._soon.start())

    @Slot()
    def configure(self):
        value = (self._store.config.get("style") or {}).get("app_themes", False)
        enabled = value is True or str(value).strip().lower() in ("true", "yes", "on")
        if os.environ.get("UNIDESK_SNAPSHOT"):
            return  # test renders never touch real settings
        if enabled and not self._enabled:
            self._enabled = True
            self._soon.start()
        elif not enabled and (self._enabled or self._state):
            self._enabled = False
            self._soon.stop()
            self.restore()

    @Slot()
    def apply(self):
        if not self._enabled:
            return
        palette = dict(self._theme.c)
        published = (tuple(palette.get(role) for role in PALETTE_ROLES), bool(self._theme.dark))
        if self._last.get(PALETTE_KEY) != published:
            try:
                publish_palette(palette, bool(self._theme.dark))
                self._last[PALETTE_KEY] = published
            except OSError as e:
                print(f"[unidesk] couldn't publish the palette: {e}")
        jobs = [(path, "vscode", vscode_colors(palette)) for path in vscode_settings()]
        jobs += [(path, "terminal", terminal_theme(palette, bool(self._theme.dark))) for path in terminal_settings()]
        for path, app, wanted in jobs:
            key = str(path)
            if self._last.get(key) == wanted:
                continue
            record = self._state.setdefault(key, {"app": app})
            try:
                (apply_vscode if app == "vscode" else apply_terminal)(path, wanted, record)
                self._last[key] = wanted
            except (OSError, ValueError, KeyError) as e:  # e.g. the file is half-edited right now
                print(f"[unidesk] couldn't theme {path}: {e}")
        self._save_state()

    @Slot()
    def restore(self):
        try:
            publish_palette(None)  # the Windhawk mod steps back
        except OSError:
            pass
        for key, record in list(self._state.items()):
            try:
                (restore_vscode if record.get("app") == "vscode" else restore_terminal)(Path(key), record)
            except (OSError, ValueError) as e:
                print(f"[unidesk] couldn't restore {key}: {e}")
                continue  # try again next time
            del self._state[key]
        self._last.clear()
        self._save_state()

    @staticmethod
    def _load_state() -> dict:
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        try:
            if self._state:
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
            else:
                STATE.unlink(missing_ok=True)
        except OSError:
            pass
