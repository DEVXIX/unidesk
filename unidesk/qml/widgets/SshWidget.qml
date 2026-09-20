import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// Terminals on the desk: one, two side by side, or four in a square.
//
// This one behaves like a window rather than like a widget. Drag its bar to
// move it, drag its corner to make it bigger, right-click it for another one -
// none of which needs edit mode, because a terminal is a thing you use, not a
// thing you arrange once and leave. Everything it does still goes through the
// frame and the config, so where you leave it is where it comes back.
//
// Each pane is its own session with its own saved connection, remembered by
// position, so a four-pane widget comes back on the same four machines.
//
// Typing is a thing you switch on. A desk window refuses the keyboard the rest
// of the time - that is what keeps the widgets out of Alt+Tab and out of the
// way of whatever you are actually working in.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    property var frame: null
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property string shape: opt("layout", "1x1")
    readonly property int columns: shape === "1x1" ? 1 : 2
    readonly property int rows: shape === "2x2" ? 2 : 1
    readonly property int paneCount: columns * rows

    // While a corner is being dragged the size is ours; on release it is
    // written to the config and these go back to nothing.
    property real heldWidth: 0
    property real heldHeight: 0
    implicitWidth: heldWidth > 0 ? heldWidth : opt("width", shape === "1x1" ? 520 : 760)
    implicitHeight: heldHeight > 0 ? heldHeight : opt("height", rows === 2 ? 480 : 300)

    property bool typing: false
    property bool menuOpen: false

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
    function setLayout(shape) {
        Desk.setOption(root.widgetId, "layout", shape);
        menuOpen = false;
    }

    // ---- the bar you drag it by -----------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 12 }
        height: 24

        // Under the buttons, so they still get their own clicks: in QML the
        // thing declared later is the thing on top.
        MouseArea {
            anchors { fill: parent; margins: -8 }
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.ArrowCursor
            property point grabbed
            property real fromX
            property real fromY
            onPressed: (e) => {
                if (e.button === Qt.RightButton) { root.menuOpen = true; return; }
                if (!root.frame) return;
                grabbed = mapToItem(root.frame.parent, e.x, e.y);
                fromX = root.frame.x;
                fromY = root.frame.y;
                root.frame.startMove();
            }
            onPositionChanged: (e) => {
                if (!pressed || !root.frame || !root.frame.dragging) return;
                var now = mapToItem(root.frame.parent, e.x, e.y);
                root.frame.moveBy(now.x - grabbed.x, now.y - grabbed.y, fromX, fromY);
            }
            onReleased: {
                if (root.frame && root.frame.dragging) root.frame.endMove(fromX, fromY);
            }
        }

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
            IconButton {
                icon: Icons.widgets; size: 24; iconSize: 14
                iconColor: Theme.c.onSurfaceVariant
                onClicked: root.menuOpen = !root.menuOpen
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

    // ---- the corner you pull ---------------------------------------------------
    Item {
        width: 22
        height: 22
        anchors { right: parent.right; bottom: parent.bottom }

        // Three little lines, the way every window that can be resized has.
        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: 2 + index * 4
                height: 2
                radius: 1
                color: corner.containsMouse ? Theme.c.primary : Theme.c.outline
                anchors.right: parent.right
                anchors.rightMargin: 6
                y: 14 - index * 4
                rotation: -45
                transformOrigin: Item.Right
            }
        }
        MouseArea {
            id: corner
            anchors.fill: parent
            anchors.margins: -6
            hoverEnabled: true
            cursorShape: Qt.SizeFDiagCursor
            preventStealing: true
            property point from
            property real wasWidth
            property real wasHeight
            onPressed: (e) => {
                from = mapToItem(null, e.x, e.y);
                wasWidth = root.width;
                wasHeight = root.height;
                root.heldWidth = wasWidth;
                root.heldHeight = wasHeight;
            }
            onPositionChanged: (e) => {
                if (!pressed) return;
                var now = mapToItem(null, e.x, e.y);
                // The frame draws the widget at Theme.scale, so a pixel on
                // screen is not a pixel of ours.
                var scale = Math.max(0.2, Theme.scale);
                root.heldWidth = Math.max(280, wasWidth + (now.x - from.x) / scale);
                root.heldHeight = Math.max(160, wasHeight + (now.y - from.y) / scale);
            }
            onReleased: {
                if (root.heldWidth <= 0) return;
                Desk.setSize(root.widgetId, Math.round(root.heldWidth), Math.round(root.heldHeight));
                root.heldWidth = 0;
                root.heldHeight = 0;
            }
        }
    }

    // ---- right-click, or the button beside Type ---------------------------------
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        z: -1              // below everything; the panes get their own clicks
        onClicked: root.menuOpen = true
    }

    Rectangle {
        id: menu
        visible: root.menuOpen
        z: 60
        anchors { right: parent.right; top: head.bottom; rightMargin: 12; topMargin: 4 }
        width: 164
        height: items.height + 12
        radius: 14
        color: Theme.c.surfaceContainerHighest
        border.width: 1
        border.color: Theme.c.outlineVariant

        Column {
            id: items
            anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 6 }

            component Entry: Rectangle {
                id: entry
                property string label: ""
                property string icon: ""
                property bool ticked: false
                signal chosen()
                width: items.width
                height: 30
                color: over.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"
                MIcon {
                    id: mark
                    anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
                    icon: entry.ticked ? Icons.check : entry.icon
                    size: 14
                    color: entry.ticked ? Theme.c.primary : Theme.c.onSurfaceVariant
                }
                UText {
                    anchors { left: mark.right; leftMargin: 8; verticalCenter: parent.verticalCenter }
                    text: entry.label
                    size: 12
                }
                MouseArea {
                    id: over
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: entry.chosen()
                }
            }

            Entry {
                label: "One pane"; icon: Icons.widgets
                ticked: root.shape === "1x1"
                onChosen: root.setLayout("1x1")
            }
            Entry {
                label: "Two panes"; icon: Icons.widgets
                ticked: root.shape === "2x1"
                onChosen: root.setLayout("2x1")
            }
            Entry {
                label: "Four panes"; icon: Icons.widgets
                ticked: root.shape === "2x2"
                onChosen: root.setLayout("2x2")
            }
            Rectangle { width: items.width; height: 1; color: Theme.c.outlineVariant }
            Entry {
                label: "New terminal"; icon: Icons.add
                onChosen: { Desk.newTerminal(root.shape); root.menuOpen = false; }
            }
            Entry {
                label: "Close this one"; icon: Icons.close
                onChosen: { root.menuOpen = false; Desk.removeWidget(root.widgetId); }
            }
        }
    }

    // Clicking anywhere else puts the menu away.
    MouseArea {
        anchors.fill: parent
        visible: root.menuOpen
        z: 55
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: root.menuOpen = false
    }
}
