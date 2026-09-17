import QtQuick
import QtQuick.Controls.Basic
import "../components"
import "../Icons.js" as Icons

// The last things you copied, newest first. Click one to copy it again.
// Always the same height (`items` rows); scroll for the rest of the history.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int rows: Math.max(1, opt("items", 5))
    readonly property real rowHeight: 60
    readonly property real gap: 6
    property real now: Date.now()

    function ago(ms) {
        var s = Math.max(0, (now - ms) / 1000);
        if (s < 60) return "just now";
        if (s < 3600) return Math.round(s / 60) + "m ago";
        if (s < 86400) return Math.round(s / 3600) + "h ago";
        return Math.round(s / 86400) + "d ago";
    }
    Timer { interval: 30000; repeat: true; running: Clipboard.items.length > 0; onTriggered: root.now = Date.now() }
    Connections {
        target: Clipboard
        function onItemsChanged() { root.now = Date.now(); list.positionViewAtBeginning(); }
    }

    implicitWidth: opt("width", 340)
    implicitHeight: list.y + list.height + 14

    Item {
        id: header
        x: 14; y: 14
        width: parent.width - 28; height: 38
        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Item {
                width: 38; height: 38
                MShape { anchors.fill: parent; shape: "flower"; color: Theme.c.primary }
                MIcon { anchors.centerIn: parent; icon: Icons.content_paste; size: 19; fill: 1; color: Theme.c.onPrimary }
            }
            UText { anchors.verticalCenter: parent.verticalCenter; text: "Clipboard"; size: 16; weight: Font.Medium }
            Rectangle {
                visible: Clipboard.items.length > root.rows
                anchors.verticalCenter: parent.verticalCenter
                height: 22; radius: 11
                width: Math.max(22, total.implicitWidth + 12)
                color: Theme.c.secondaryContainer
                UText { id: total; anchors.centerIn: parent; text: Clipboard.items.length; size: 12; weight: Font.Medium; color: Theme.c.onSecondaryContainer }
            }
        }
        IconButton {
            visible: Clipboard.items.length > 0
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            icon: Icons.delete_sweep; size: 34; iconSize: 19
            iconColor: Theme.c.onSurfaceVariant
            onClicked: Clipboard.clear()
        }
    }

    ListView {
        id: list
        x: 14
        y: header.y + header.height + 10
        width: parent.width - 28
        height: root.rows * root.rowHeight + (root.rows - 1) * root.gap
        clip: true
        spacing: root.gap
        boundsBehavior: Flickable.StopAtBounds
        model: Clipboard.items

        ScrollBar.vertical: ScrollBar {
            id: scroller
            policy: list.contentHeight > list.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            width: 6
            background: null
            contentItem: Rectangle { implicitWidth: 4; radius: 2; color: Theme.c.onSurfaceVariant; opacity: scroller.pressed ? 0.6 : 0.35 }
        }

        delegate: Item {
            id: entry
            required property var modelData
            readonly property bool picture: modelData.thumb !== ""   // copied pictures, and copied image files
            readonly property bool copied: Clipboard.copied === modelData.id
            width: list.width - (scroller.visible ? 10 : 0)
            height: root.rowHeight

            HoverHandler { id: hover }
            Rectangle {
                anchors.fill: parent
                radius: 16
                color: entry.copied ? Theme.c.secondaryContainer : Theme.c.surfaceContainerHighest
                opacity: entry.copied || hover.hovered ? 1 : 0.55
                Behavior on color { ColorAnimation { duration: 200 } }
                Behavior on opacity { NumberAnimation { duration: 150 } }
            }
            Item {
                id: preview
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                width: entry.picture ? 68 : 40
                height: entry.picture ? 46 : 40
                ShapedImage { anchors.fill: parent; visible: entry.picture; radius: 10; source: entry.modelData.thumb }
                Rectangle {
                    anchors.fill: parent
                    visible: !entry.picture
                    radius: 12
                    color: Theme.c.primaryContainer
                    MIcon { anchors.centerIn: parent; icon: entry.modelData.kind === "files" ? Icons.folder : Icons.notes; size: 19; color: Theme.c.onPrimaryContainer }
                }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Clipboard.copy(entry.modelData.id) }
            Column {
                anchors { left: preview.right; leftMargin: 12; right: actions.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                UText {
                    width: parent.width
                    text: entry.modelData.text
                    textFormat: Text.PlainText
                    size: 14
                    color: entry.copied ? Theme.c.onSecondaryContainer : Theme.c.onSurface
                }
                UText {
                    width: parent.width
                    text: entry.copied ? "Copied" : root.ago(entry.modelData.at) + "  ·  " + entry.modelData.detail
                    textFormat: Text.PlainText
                    size: 12
                    color: entry.copied ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant
                }
            }
            Item {
                id: actions
                anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                width: 30; height: 30
                MIcon { anchors.centerIn: parent; visible: entry.copied; icon: Icons.check; size: 20; color: Theme.c.onSecondaryContainer }
                IconButton {
                    anchors.fill: parent
                    visible: !entry.copied && hover.hovered
                    icon: Icons.close; iconSize: 17
                    iconColor: Theme.c.onSurfaceVariant
                    onClicked: Clipboard.remove(entry.modelData.id)
                }
            }
        }
    }

    UText {
        visible: Clipboard.items.length === 0
        anchors.centerIn: list
        width: list.width - 24
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: "Copy some text, a picture or files and they show up here"
        size: 13.5
        color: Theme.c.onSurfaceVariant
    }
}
