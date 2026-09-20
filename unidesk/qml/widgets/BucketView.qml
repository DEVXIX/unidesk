import QtQuick
import "../components"
import "../Icons.js" as Icons

// The inside of an S3 connection: what is in this bucket, or why it is not
// showing anything. Used by the storage widget and by any terminal pane that
// has been pointed at a bucket instead of a machine.
//
// It browses. Clicking a folder goes in, clicking a file downloads it, and
// there is deliberately nothing here that deletes or overwrites: a pane you
// click by accident should not be able to lose anything.
Item {
    id: view
    property string ident: ""
    property bool compact: false

    property string phase: "idle"
    property string message: ""
    property var entries: []

    function refresh() {
        if (ident === "") return;
        phase = Buckets.state(ident);
        message = Buckets.message(ident);
        entries = Buckets.entries(ident);
    }
    Component.onCompleted: refresh()
    onIdentChanged: refresh()

    Connections {
        target: Buckets
        function onStateChanged(who) { if (who === view.ident) view.refresh(); }
    }

    function sizeOf(bytes) {
        if (!bytes) return "";
        var units = ["B", "KB", "MB", "GB", "TB"], n = bytes, i = 0;
        while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
        return (i === 0 ? n : n.toFixed(n < 10 ? 1 : 0)) + " " + units[i];
    }

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        spacing: 1
        visible: view.entries.length > 0
        model: view.entries

        delegate: Rectangle {
            required property var modelData
            width: list.width
            height: view.compact ? 26 : 32
            radius: 8
            color: hover.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"

            readonly property bool isFile: modelData.kind === "object"

            MIcon {
                id: kindIcon
                anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                icon: modelData.kind === "bucket" ? Icons.hard_drive
                    : modelData.kind === "folder" ? Icons.folder : Icons.description
                size: view.compact ? 13 : 15
                color: parent.isFile ? Theme.c.onSurfaceVariant : Theme.c.primary
            }
            UText {
                anchors { left: kindIcon.right; leftMargin: 8; right: size.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                text: modelData.name
                size: view.compact ? 11 : 12
                elide: Text.ElideMiddle
            }
            UText {
                id: size
                anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                text: hover.containsMouse && parent.isFile ? "Download" : view.sizeOf(modelData.size)
                size: view.compact ? 9.5 : 10
                color: hover.containsMouse && parent.isFile ? Theme.c.primary : Theme.c.onSurfaceVariant
            }
            MouseArea {
                id: hover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (parent.isFile) Buckets.download(view.ident, modelData.name);
                    else Buckets.enter(view.ident, modelData.name);
                }
            }
        }
    }

    // Busy, empty, or broken.
    Column {
        anchors.centerIn: parent
        width: parent.width - 24
        spacing: 5
        visible: !list.visible

        UText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: view.phase === "connecting" ? "Connecting..."
                : view.phase === "loading" ? "Loading..."
                : view.phase === "failed" ? "That did not work" : "Nothing here"
            size: view.compact ? 11.5 : 13
            weight: Font.Medium
        }
        UText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            text: view.message
            size: view.compact ? 9.5 : 10.5
            color: Theme.c.onSurfaceVariant
        }
    }
}
