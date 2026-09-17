# unidesk

Desktop widgets, a dock and search for Windows 11, in a Material You style. Colours follow your album art or wallpaper.

- **Widgets on the wallpaper:**
  - time and an analog clock
  - music with synced lyrics
  - weather, CPU / RAM / GPU and a calendar
  - network speed, storage, clipboard history and notifications
  - a profile card
  - GitHub + Gitea activity
  - picture frames
- **A dock** that replaces the taskbar:
  - pinned and running apps with unread badges
  - live window previews
  - now playing, a clock and quick settings
- **Every monitor:** widgets and a dock on each screen. Drag a widget onto another screen to move it there. Widgets keep their distance from the nearest edge, so layouts fit wide and ultrawide monitors.
- **Matching windows:** other apps' title bars and borders take the same colours (Windows 11). Optionally, VS Code and Windows Terminal are themed too (title bar, menus, tabs, status bar and scroll bars). With the [Windhawk mod](windhawk/README.md), so are classic apps' menus, scroll bars, status bars and toolbars.
- **Search** (Alt+Space): apps, maths, Windows settings, files and the web.
- **Low overhead:** it is Qt Quick (PySide6), not a browser. Each screen goes idle while a game or video is fullscreen on it.

## Install

Download `unidesk-setup-x.y.z.exe` from [Releases](https://github.com/DEVXIX/unidesk/releases). It installs for your account only, with no admin rights needed. It updates itself when a new release is published.

The READ-ME that opens after installing lists all the shortcuts. The short version:

| Shortcut / action | What it does |
| --- | --- |
| Alt + Space | search |
| Ctrl + Alt + E | edit mode: move, resize, add or remove widgets, and open Settings |
| Right-click a widget | its options |

Your settings live in `%USERPROFILE%\.config\unidesk\config.yaml`. The file is live-reloaded, and every option is commented. Use the tray menu's **Export / Import settings** to share a setup without your tokens.

## Run from source

```powershell
pip install -r requirements.txt
dotnet publish media-bridge -c Release -o resources/media-bridge   # now-playing bridge (.NET 9 SDK)
python tools\build_fonts.py                                         # needs the font sources in tools\fonts-src
pythonw unidesk.pyw
```

## Build and release

```powershell
powershell -ExecutionPolicy Bypass -File tools\build.ps1     # dist\unidesk-setup-<version>.exe
powershell -ExecutionPolicy Bypass -File tools\release.ps1 -Notes "What changed"
```

`release.ps1` does four things:

1. builds the installer
2. tags the version from `unidesk/__init__.py`
3. pushes the tag
4. creates a GitHub Release with the installer attached

Installed copies pick it up on their next update check.

## Credits

- Visual direction: [end-4's dots](https://github.com/end-4/dots-hyprland) and [pctrade/end4-pC](https://github.com/pctrade/end4-pC)
- Fonts: Google Sans Flex and Material Symbols Rounded (SIL OFL / Apache 2.0)
- Colours: [materialyoucolor](https://github.com/T-Dark0/materialyoucolor-python)
- Lyrics: [lrclib.net](https://lrclib.net)
- Weather: [Open-Meteo](https://open-meteo.com)
