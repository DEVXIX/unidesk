import QtQuick
import QtQuick.Controls.Basic
import "../components"
import "../Icons.js" as Icons

// What's waiting in Notification Center, newest first. Click one to open its
// app. Always the same height (room for `items` notifications); scroll for more.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int rows: Math.max(1, opt("items", 4))
    readonly property bool messages: opt("text", true)
    readonly property real rowHeight: messages ? 92 : 58
    readonly property real gap: 6
    property real now: Date.now()

    function ago(ms) {
        var s = Math.max(0, (now - ms) / 1000);
        if (s < 60) return "now";
        if (s < 3600) return Math.round(s / 60) + "m";
        if (s < 86400) return Math.round(s / 3600) + "h";
        return Math.round(s / 86400) + "d";
    }
    Timer { interval: 30000; repeat: true; running: Notifications.items.length > 0; onTriggered: root.now = Date.now() }
    Connections {
        target: Notifications
        function onChanged() { root.now = Date.now(); list.positionViewAtBeginning(); }
    }

    implicitWidth: opt("width", 360)
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
                MIcon { anchors.centerIn: parent; icon: Icons.notifications; size: 19; fill: 1; color: Theme.c.onPrimary }
            }
            UText { anchors.verticalCenter: parent.verticalCenter; text: "Notifications"; size: 16; weight: Font.Medium }
            Rectangle {
                visible: Notifications.items.length > 0
                anchors.verticalCenter: parent.verticalCenter
                height: 22; radius: 11
                width: Math.max(22, count.implicitWidth + 12)
                color: Theme.c.tertiaryContainer
                UText { id: count; anchors.centerIn: parent; text: Notifications.items.length; size: 12; weight: Font.Medium; color: Theme.c.onTertiaryContainer }
            }
        }
        Row {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: 2
            IconButton {
                visible: Notifications.items.length > 0
                icon: Icons.clear_all; size: 34; iconSize: 19
                iconColor: Theme.c.onSurfaceVariant
                onClicked: Notifications.clear()
            }
            IconButton {
                icon: Icons.open_in_new; size: 34; iconSize: 18
                iconColor: Theme.c.onSurfaceVariant
                onClicked: Notifications.openCenter()
            }
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
        model: Notifications.items

        ScrollBar.vertical: ScrollBar {
            id: scroller
            policy: list.contentHeight > list.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            width: 6
            background: null
            contentItem: Rectangle { implicitWidth: 4; radius: 2; color: Theme.c.onSurfaceVariant; opacity: scroller.pressed ? 0.6 : 0.35 }
        }

        delegate: Item {
            id: note
            required property var modelData
            width: list.width - (scroller.visible ? 10 : 0)
            height: Math.max(56, body.implicitHeight + 20)

            HoverHandler { id: hover }
            Rectangle {
                anchors.fill: parent
                radius: 18
                color: Theme.c.surfaceContainerHighest
                opacity: hover.hovered ? 1 : 0.55
                Behavior on opacity { NumberAnimation { duration: 150 } }
            }
            Item {
                id: appIcon
                x: 10; y: 10
                width: 36; height: 36
                Image {
                    anchors.fill: parent
                    visible: note.modelData.icon !== ""
                    source: note.modelData.icon
                    sourceSize: Qt.size(72, 72)
                    smooth: true; mipmap: true
                    asynchronous: true
                }
                MShape { anchors.fill: parent; visible: note.modelData.icon === ""; shape: "cookie12"; color: Theme.c.secondaryContainer }
                MIcon { anchors.centerIn: parent; visible: note.modelData.icon === ""; icon: Icons.notifications; size: 18; color: Theme.c.onSecondaryContainer }
            }
            Column {
                id: body
                anchors { left: appIcon.right; leftMargin: 12; right: parent.right; rightMargin: 12; top: parent.top; topMargin: 10 }
                spacing: 1
                Item {
                    width: parent.width; height: appName.implicitHeight
                    UText { id: appName; width: parent.width - when.implicitWidth - 8; text: note.modelData.app; textFormat: Text.PlainText; size: 12; color: Theme.c.onSurfaceVariant }
                    UText { id: when; anchors.right: parent.right; text: root.ago(note.modelData.at); size: 12; color: Theme.c.onSurfaceVariant }
                }
                UText { width: parent.width; text: note.modelData.title; textFormat: Text.PlainText; size: 14.5; weight: Font.Medium }
                UText {
                    visible: root.messages && note.modelData.body !== ""
                    width: parent.width
                    text: note.modelData.body
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    size: 13
                    color: Theme.c.onSurfaceVariant
                }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Notifications.open(note.modelData.id) }
        }
    }

    Column {
        visible: Notifications.items.length === 0
        anchors.centerIn: list
        spacing: 6
        MIcon { anchors.horizontalCenter: parent.horizontalCenter; icon: Icons.notifications_off; size: 26; color: Theme.c.onSurfaceVariant }
        UText {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Notifications.available ? "You're all caught up" : "Notifications can't be read on this PC"
            size: 13.5
            color: Theme.c.onSurfaceVariant
        }
    }
}
