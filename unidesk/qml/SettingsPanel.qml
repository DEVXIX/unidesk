import QtQuick
import "components"
import "Icons.js" as Icons

// Desk-wide settings: look, weather, Git accounts. Writes to config.yaml.
Card {
    id: panel
    signal close()

    tone: "surface"
    width: 360
    height: Math.min(parent ? parent.height - 100 : 760, body.implicitHeight + 32)

    readonly property var cfg: Desk.config
    function get(path) {
        var node = cfg;
        var keys = path.split(".");
        for (var i = 0; i < keys.length; i++) {
            if (node === undefined || node === null) return undefined;
            node = node[keys[i]];
        }
        return node;
    }

    readonly property var sections: [
        { title: "Look", fields: [
            { path: "theme.source", label: "Colours from", kind: "choice", options: ["artwork", "wallpaper", "color"], def: "artwork" },
            { path: "theme.color", label: "Colour (hex, used for 'color')", kind: "text", def: "#b5485d" },
            { path: "theme.mode", label: "Mode", kind: "choice", options: ["dark", "light"], def: "dark" },
            { path: "theme.scheme", label: "Palette", kind: "choice", options: ["tonal-spot", "vibrant", "expressive", "fidelity", "content", "neutral"], def: "tonal-spot" },
            { path: "style.scale", label: "Size of everything", kind: "slider", min: 0.5, max: 2, step: 0.05, def: 1 },
            { path: "style.radius", label: "Corner roundness", kind: "slider", min: 0, max: 44, step: 2, def: 28 },
            { path: "style.card_opacity", label: "Card opacity", kind: "slider", min: 0.3, max: 1, step: 0.02, def: 0.92 },
            { path: "style.font_roundness", label: "Rounded letters", kind: "slider", min: 0, max: 100, step: 5, def: 60 },
            { path: "style.shadows", label: "Shadows", kind: "bool", def: true },
            { path: "style.window_frames", label: "Other apps' title bars and borders", kind: "choice", options: ["themed", "border", "off"], def: "themed" },
            { path: "style.window_buttons", label: "Cookie buttons on the active window (Explorer, dialogs, classic apps)", kind: "bool", def: false },
            { path: "style.app_themes", label: "Theme other apps (VS Code, Terminal, classic apps with the Windhawk mod)", kind: "bool", def: false },
            { path: "lock_screen.enabled", label: "Put your desk on the Windows lock screen (a picture of it, repainted now and then)", kind: "bool", def: false },
            { path: "lock_screen.every_minutes", label: "Repaint the lock screen every (minutes)", kind: "slider", min: 1, max: 60, step: 1, def: 10 }
        ]},
        { title: "Dock", fields: [
            { path: "dock.enabled", label: "Show the dock", kind: "bool", def: true },
            { path: "dock.all_screens", label: "A dock on every screen", kind: "bool", def: true },
            { path: "dock.apps", label: "Apps on each dock", kind: "choice", options: ["all", "screen"], def: "all" },
            { path: "dock.hide_windows_taskbar", label: "Hide the Windows taskbar", kind: "bool", def: true },
            { path: "dock.icon_size", label: "Icon size", kind: "slider", min: 28, max: 64, step: 2, def: 40 },
            { path: "dock.zoom", label: "Hover zoom", kind: "slider", min: 1, max: 1.8, step: 0.05, def: 1.3 },
            { path: "dock.badges", label: "Unread badges", kind: "bool", def: true },
            { path: "dock.now_playing", label: "Now playing", kind: "bool", def: true },
            { path: "dock.search", label: "Search box", kind: "bool", def: true },
            { path: "dock.clock_format", label: "Dock clock", kind: "choice", options: ["12h", "24h"], def: "12h" },
            { path: "dock.clock_seconds", label: "Seconds on the clock", kind: "bool", def: false },
            { path: "dock.auto_hide", label: "Hide the dock until you reach the bottom edge", kind: "bool", def: false },
            { path: "dock.reserve_space", label: "Keep windows above the dock", kind: "bool", def: true }
        ]},
        { title: "Search", fields: [
            { path: "search.enabled", label: "Use unidesk search", kind: "bool", def: true },
            { path: "search.hotkey", label: "Hotkey (restart to apply)", kind: "text", def: "alt+space" },
            { path: "search.web", label: "Web search URL ({q} = your text)", kind: "text", def: "https://www.google.com/search?q={q}" }
        ]},
        { title: "Weather", fields: [
            { path: "settings.weather.location", label: "Location (auto, city, or lat,lon)", kind: "text", def: "auto" },
            { path: "settings.weather.units", label: "Units", kind: "choice", options: ["metric", "imperial"], def: "metric" }
        ]},
        { title: "Code activity", fields: [
            { path: "settings.git.source", label: "Show", kind: "choice", options: ["gitea", "github", "both"], def: "github" },
            { path: "settings.git.profile", label: "Profile (name + avatar) from", kind: "choice", options: ["github", "gitea"], def: "github" },
            { path: "settings.git.gitea_url", label: "Gitea URL", kind: "text", def: "" },
            { path: "settings.git.gitea_token", label: "Gitea access token", kind: "secret", def: "" },
            { path: "settings.git.github_user", label: "GitHub username", kind: "text", def: "" },
            { path: "settings.git.github_token", label: "GitHub token (optional)", kind: "secret", def: "" }
        ]}
    ]

    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: (w) => w.accepted = true }

    Flickable {
        anchors.fill: parent
        anchors.margins: 16
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            width: parent.width
            spacing: 14

            Item {
                width: parent.width; height: 40
                UText { anchors.verticalCenter: parent.verticalCenter; text: "Settings"; size: 21; weight: Font.Medium }
                IconButton {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    icon: Icons.close; size: 36
                    onClicked: panel.close()
                }
            }

            Rectangle {
                width: parent.width
                height: 56
                radius: 18
                color: Updater.state === "available" ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                Column {
                    anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                    UText { text: "unidesk " + Updater.current; size: 14; weight: Font.Medium; color: Updater.state === "available" ? Theme.c.onPrimaryContainer : Theme.c.onSurface }
                    UText {
                        text: ({
                            available: "Version " + Updater.version + " is available",
                            downloading: "Downloading " + Math.round(Updater.progress * 100) + "%",
                            installing: "Installing, unidesk will restart",
                            error: "Update failed: " + Updater.error
                        })[Updater.state] || "Up to date"
                        size: 12
                        color: Updater.state === "available" ? Theme.c.onPrimaryContainer : Theme.c.onSurfaceVariant
                    }
                }
                Rectangle {
                    anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    width: updateText.implicitWidth + 28; height: 36; radius: 18
                    color: Theme.c.primary
                    opacity: Updater.state === "downloading" || Updater.state === "installing" ? 0.5 : 1
                    UText { id: updateText; anchors.centerIn: parent; text: Updater.state === "available" || Updater.state === "error" ? "Update" : "Check"; size: 13.5; weight: Font.Medium; color: Theme.c.onPrimary }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: (Updater.state === "available" || Updater.state === "error") ? Updater.install() : Updater.check()
                    }
                }
            }

            Repeater {
                model: panel.sections
                Column {
                    required property var modelData
                    width: body.width
                    spacing: 12
                    UText { text: modelData.title; size: 13; weight: Font.DemiBold; color: Theme.c.primary; topPadding: 6 }
                    Repeater {
                        model: modelData.fields
                        OptionRow {
                            required property var modelData
                            width: body.width
                            field: modelData
                            value: panel.get(modelData.path)
                            onChanged: (v) => Desk.setSetting(modelData.path, v)
                        }
                    }
                }
            }

            UText {
                width: parent.width
                visible: GitHub.error !== ""
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                text: GitHub.error
                size: 12.5
                color: Theme.c.error
            }
            UText {
                width: parent.width
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                text: "Tokens are saved in config.yaml on this PC."
                size: 12
                color: Theme.c.onSurfaceVariant
            }
        }
    }
}
