import QtQuick
import "../components"
import "../Icons.js" as Icons

// A grid of shortcuts. Option items: one per line, "path, URL or app" or
// "Name | target" (e.g. "Downloads | %USERPROFILE%\Downloads").
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int columns: opt("columns", 4)
    readonly property real tile: opt("tile", 76)
    readonly property var entries: {
        var raw = String(opt("items", "%USERPROFILE%\\Downloads\nms-settings:\nhttps://github.com\nC:\\Windows\\explorer.exe"));
        var out = [];
        raw.split(/\r?\n/).forEach(function (line) {
            line = line.trim();
            if (!line) return;
            var bar = line.indexOf("|");
            var name = bar >= 0 ? line.slice(0, bar).trim() : "";
            var target = bar >= 0 ? line.slice(bar + 1).trim() : line;
            if (!name) {
                var clean = target.replace(/[\\/]+$/, "");
                name = /^https?:\/\//.test(target) ? target.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]
                     : /^ms-settings:/.test(target) ? "Settings"
                     : clean.split(/[\\/]/).pop().replace(/\.(exe|lnk)$/i, "");
            }
            out.push({ name: name, target: target });
        });
        return out;
    }

    implicitWidth: columns * tile + (columns - 1) * 6 + 24
    implicitHeight: grid.implicitHeight + 24

    Grid {
        id: grid
        x: 12; y: 12
        columns: root.columns
        spacing: 6
        Repeater {
            model: root.entries
            delegate: Item {
                required property var modelData
                readonly property string icon: Desk.iconFor(modelData.target)
                width: root.tile; height: root.tile + 8
                Rectangle { anchors.fill: parent; radius: 18; color: Theme.c.onSurface; opacity: tileMouse.containsMouse ? 0.07 : 0 }
                Image {
                    id: img
                    anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: 10 }
                    width: root.tile * 0.46; height: width
                    source: parent.icon
                    sourceSize: Qt.size(96, 96)
                    smooth: true; mipmap: true
                    visible: parent.icon !== ""
                    scale: tileMouse.pressed ? 0.9 : tileMouse.containsMouse ? 1.08 : 1
                    Behavior on scale { NumberAnimation { duration: 150 } }
                }
                Item {
                    visible: !img.visible
                    anchors.centerIn: img
                    width: img.width; height: width
                    MShape { anchors.fill: parent; shape: "cookie12"; color: Theme.c.primaryContainer }
                    MIcon {
                        anchors.centerIn: parent
                        icon: /^https?:/.test(modelData.target) ? Icons.language : /^ms-settings/.test(modelData.target) ? Icons.settings : Icons.folder
                        size: 18; color: Theme.c.onPrimaryContainer
                    }
                }
                UText {
                    anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 8 }
                    width: parent.width - 8
                    horizontalAlignment: Text.AlignHCenter
                    text: modelData.name
                    size: 11.5
                }
                MouseArea { id: tileMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Desk.launch(modelData.target) }
            }
        }
    }
}
