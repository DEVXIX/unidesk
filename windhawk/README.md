# unidesk colours for classic apps (Windhawk mod)

Paints the parts of classic Windows apps that Windows' theme draws in unidesk's
live Material You colours:

- menu bars and every drop-down and right-click menu
- scroll bars
- status bars
- toolbars

It works in any app built on standard Windows controls, such as Notepad++,
TextPad, Registry Editor, installers, older tools, and many right-click menus.
It can't reach apps that draw their own interface: browsers, Electron apps like
VS Code, Discord or Docker Desktop, and new Windows 11 apps like Paint or
Settings. unidesk themes VS Code and Windows Terminal itself.

## Install

1. In unidesk: **Ctrl+Alt+E**, then the gear icon, and turn on **Theme other apps**.
   unidesk then publishes its colours for the mod, and updates them with every
   palette change.
2. In [Windhawk](https://windhawk.net), click **Create a New Mod**.
3. Replace the example code with the contents of `unidesk-classic-ui.wh.cpp`.
4. Click **Compile Mod**, then **Exit Editing Mode**. The mod is on.

Open apps change the next time they redraw; if one doesn't, restart it. Each
area can be switched off in the mod's **Settings** tab in Windhawk.

To update the mod after changing this file: open the mod's **Details** in
Windhawk, click **Edit**, paste the new code, click **Compile Mod**, then
**Exit Editing Mode**.

## Turning it off

Disable or delete the mod in Windhawk, or turn off **Theme other apps** in
unidesk. Apps go back to their own look.
