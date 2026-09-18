import QtQuick
import "../components"
import "../Icons.js" as Icons

// What xD wants you to know: the notification badge and the latest of them.
// Clicking one hands it to the website, because acting on a notification is
// rarely something a widget can finish.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int rows: Math.max(1, opt("items", 4))
    implicitWidth: opt("width", 320)
    implicitHeight: 52 + rows * 48

    function textOf(row) {
        return row.message || row.text || row.body || row.title || row.type || "Something happened";
    }
    function whoOf(row) {
        var u = row.user || row.actor || row.from;
        if (!u) return "";
        return typeof u === "string" ? u : (u.username || u.name || "");
    }

    Row {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 14 }
        height: 24
        spacing: 8
        MIcon { icon: Icons.notifications; size: 18; color: Theme.c.primary; anchors.verticalCenter: parent.verticalCenter }
        UText { text: "xD"; size: 15; weight: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
        Rectangle {
            visible: XD.badge > 0
            height: 20; radius: 10
            width: Math.max(20, count.implicitWidth + 12)
            color: Theme.c.error
            anchors.verticalCenter: parent.verticalCenter
            UText { id: count; anchors.centerIn: parent; text: XD.badge; size: 11; weight: Font.Bold; color: Theme.c.onError }
        }
    }

    UText {
        anchors { top: head.bottom; topMargin: 14; horizontalCenter: parent.horizontalCenter }
        visible: !XD.signedIn
        text: "Sign in from the xD chat widget."
        size: 12
        color: Theme.c.onSurfaceVariant
    }

    ListView {
        anchors { top: head.bottom; topMargin: 8; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 14; topMargin: 8 }
        visible: XD.signedIn
        clip: true
        spacing: 2
        model: XD.notifications
        delegate: Item {
            required property var modelData
            width: ListView.view.width
            height: 46
            Rectangle { anchors.fill: parent; radius: 10; color: Theme.c.onSurface; opacity: hit.containsMouse ? 0.07 : 0 }
            Column {
                anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                spacing: 1
                UText {
                    width: parent.width
                    text: root.textOf(modelData)
                    size: 12.5
                    elide: Text.ElideRight
                }
                UText {
                    width: parent.width
                    visible: root.whoOf(modelData) !== ""
                    text: "@" + root.whoOf(modelData)
                    size: 11
                    color: Theme.c.onSurfaceVariant
                    elide: Text.ElideRight
                }
            }
            MouseArea {
                id: hit
                anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                onClicked: XD.open("notifications")
            }
        }
    }

    UText {
        anchors.centerIn: parent
        visible: XD.signedIn && XD.notifications.length === 0
        text: "Nothing new"
        size: 12
        color: Theme.c.onSurfaceVariant
    }
}
