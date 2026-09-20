import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// Terminals on the desk: one, two side by side, or four in a square.
//
// Each pane is its own session with its own saved connection, so a widget can
// be one machine you watch all day or four you jump between. Which connection
// each pane holds is remembered in the widget's own options, so the desk comes
// back the way you left it.
//
// Typing is a thing you switch on. A desk window refuses the keyboard the rest
// of the time - that is what keeps the widgets out of Alt+Tab and out of the
// way of whatever you are actually working in - and a terminal is the one
// widget that has to ask for it back.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property string shape: opt("layout", "1x1")
    readonly property int columns: shape === "1x1" ? 1 : 2
    readonly property int rows: shape === "2x2" ? 2 : 1
    readonly property int paneCount: columns * rows

    implicitWidth: opt("width", shape === "1x1" ? 520 : 760)
    implicitHeight: opt("height", rows === 2 ? 480 : 300)

    property bool typing: false

    // Which saved connection each pane is on, by position.
    readonly property var connections: {
        var saved = opt("panes", []);
        var out = [];
        for (var i = 0; i < paneCount; i++) out.push(saved && saved[i] ? String(saved[i]) : "");
        return out;
    }
    function remember(index, name) {
        if (root.connections[index] === name) return;   // nothing to write down
        var out = [];
        for (var i = 0; i < paneCount; i++) out.push(i === index ? name : root.connections[i]);
        Desk.setOption(root.widgetId, "panes", out);
    }

    // ---- header ---------------------------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 12 }
        height: 24

        MIcon {
            id: lead
            anchors.verticalCenter: parent.verticalCenter
            icon: Icons.terminal
            size: 17
            color: root.typing ? Theme.c.primary : Theme.c.onSurfaceVariant
        }
        UText {
            anchors { left: lead.right; leftMargin: 8; right: tools.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
            text: root.opt("label", "") || "Terminal"
            size: 15; weight: Font.Medium
        }

        Row {
            id: tools
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: 2

            // What it costs to type here is that the desk can be focused, so
            // it says so rather than doing it quietly.
            Rectangle {
                width: typeRow.width + 14; height: 22; radius: 11
                color: root.typing ? Theme.c.primary : "transparent"
                border.width: root.typing ? 0 : 1.5
                border.color: Theme.c.outline
                Row {
                    id: typeRow
                    anchors.centerIn: parent
                    spacing: 4
                    MIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons.keyboard; size: 13
                        color: root.typing ? Theme.c.onPrimary : Theme.c.onSurfaceVariant
                    }
                    UText {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.typing ? "Typing" : "Type"
                        size: 10.5; weight: Font.Medium
                        color: root.typing ? Theme.c.onPrimary : Theme.c.onSurfaceVariant
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.typing = !root.typing;
                        Desk.focusInput(Window.window, root.typing);
                    }
                }
            }
        }
    }

    // Leaving the keyboard behind when the widget goes away, or the desk
    // would stay focusable for good.
    Component.onDestruction: if (root.typing && Window.window) Desk.focusInput(Window.window, false);

    // ---- the panes ------------------------------------------------------------
    Grid {
        id: grid
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
        anchors { top: head.bottom; topMargin: 8 }
        columns: root.columns
        rows: root.rows
        spacing: 8

        readonly property real cellWidth: (width - spacing * (root.columns - 1)) / root.columns
        readonly property real cellHeight: (height - spacing * (root.rows - 1)) / root.rows

        Repeater {
            model: root.paneCount
            TerminalPane {
                required property int index
                width: grid.cellWidth
                height: grid.cellHeight
                paneId: root.widgetId + ":" + index
                connectionName: root.connections[index]
                typing: root.typing
                compact: root.paneCount > 1
                onChose: (name) => root.remember(index, name)
                onCleared: root.remember(index, "")
            }
        }
    }
}
