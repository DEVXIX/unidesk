import QtQuick
import QtQuick.Controls.Basic
import "../components"
import "../Icons.js" as Icons

// Your xD messages. The conversation list until you pick somebody, then that
// conversation with a box to answer in. Signing in happens here rather than in
// settings, because this is where you notice you are signed out.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int rows: Math.max(2, opt("items", 5))
    implicitWidth: opt("width", 340)
    implicitHeight: 54 + rows * 56 + (XD.signedIn ? 44 : 0)

    // Reading a conversation is a thing you do, so it is not remembered: the
    // widget goes back to the list rather than sitting in somebody's thread.
    property string openWith: ""

    function nameOf(row) {
        return row.username || row.handle || row.name || row.user || "";
    }
    function textOf(row) {
        return row.content || row.text || row.body || row.message || "";
    }

    Connections {
        target: XD
        function onThreadChanged() { messages.positionViewAtEnd(); }
    }

    // ---- signed out ----------------------------------------------------------
    Column {
        anchors { fill: parent; margins: 14 }
        spacing: 8
        visible: !XD.signedIn

        Row {
            spacing: 8
            MIcon { icon: Icons.comment; size: 18; color: Theme.c.primary; anchors.verticalCenter: parent.verticalCenter }
            UText { text: "xD"; size: 15; weight: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
        }
        UText {
            width: parent.width
            text: XD.error !== "" ? XD.error : "Sign in to read your messages."
            size: 12
            wrapMode: Text.WordWrap
            color: XD.error !== "" ? Theme.c.error : Theme.c.onSurfaceVariant
        }
        Field { id: userField; width: parent.width; placeholder: "username" }
        Field { id: passField; width: parent.width; placeholder: "password"; secret: true
                onAccepted: XD.signIn(userField.text, passField.text) }
        Rectangle {
            width: parent.width; height: 34; radius: 17
            color: XD.busy ? Theme.c.surfaceContainerHighest : Theme.c.primary
            UText {
                anchors.centerIn: parent
                text: XD.busy ? "Signing in…" : "Sign in"
                size: 13; weight: Font.Medium
                color: XD.busy ? Theme.c.onSurfaceVariant : Theme.c.onPrimary
            }
            MouseArea {
                anchors.fill: parent
                enabled: !XD.busy
                cursorShape: Qt.PointingHandCursor
                onClicked: XD.signIn(userField.text, passField.text)
            }
        }
    }

    // ---- signed in -----------------------------------------------------------
    Item {
        anchors { fill: parent; margins: 14 }
        visible: XD.signedIn

        Row {
            id: head
            width: parent.width
            height: 28
            spacing: 8

            MIcon {
                icon: root.openWith === "" ? Icons.comment : Icons.close
                size: 18
                color: Theme.c.primary
                anchors.verticalCenter: parent.verticalCenter
                MouseArea {
                    anchors.fill: parent; anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.openWith = ""
                }
            }
            UText {
                text: root.openWith === "" ? "Messages" : "@" + root.openWith
                size: 15; weight: Font.Medium
                anchors.verticalCenter: parent.verticalCenter
            }
            Rectangle {
                visible: XD.unread > 0 && root.openWith === ""
                height: 20; radius: 10
                width: Math.max(20, badge.implicitWidth + 12)
                color: Theme.c.primary
                anchors.verticalCenter: parent.verticalCenter
                UText { id: badge; anchors.centerIn: parent; text: XD.unread; size: 11; weight: Font.Bold; color: Theme.c.onPrimary }
            }
        }

        // the conversation list
        ListView {
            anchors { top: head.bottom; topMargin: 8; left: parent.left; right: parent.right; bottom: parent.bottom }
            visible: root.openWith === ""
            clip: true
            spacing: 4
            model: XD.conversations
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 52
                Rectangle { anchors.fill: parent; radius: 12; color: Theme.c.onSurface; opacity: row.containsMouse ? 0.07 : 0 }
                Column {
                    anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
                    width: parent.width - 20
                    spacing: 2
                    UText { text: root.nameOf(modelData) || "someone"; size: 13.5; weight: Font.Medium; elide: Text.ElideRight; width: parent.width }
                    UText { text: root.textOf(modelData); size: 11.5; color: Theme.c.onSurfaceVariant; elide: Text.ElideRight; width: parent.width }
                }
                MouseArea {
                    id: row
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { root.openWith = root.nameOf(modelData); XD.openThread(root.openWith); }
                }
            }
        }

        // one conversation
        ListView {
            id: messages
            anchors { top: head.bottom; topMargin: 8; left: parent.left; right: parent.right; bottom: composer.top; bottomMargin: 8 }
            visible: root.openWith !== ""
            clip: true
            spacing: 4
            model: XD.thread
            delegate: Item {
                required property var modelData
                readonly property bool mine: root.nameOf(modelData) === XD.me
                width: ListView.view.width
                height: bubble.height
                Rectangle {
                    id: bubble
                    x: parent.mine ? parent.width - width : 0
                    width: Math.min(parent.width * 0.85, line.implicitWidth + 20)
                    height: line.implicitHeight + 14
                    radius: 14
                    color: parent.mine ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                    UText {
                        id: line
                        anchors { centerIn: parent; margins: 10 }
                        width: bubble.width - 20
                        text: root.textOf(modelData)
                        size: 12.5
                        wrapMode: Text.WordWrap
                        color: parent.parent.mine ? Theme.c.onPrimaryContainer : Theme.c.onSurface
                    }
                }
            }
        }

        Field {
            id: composer
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            visible: root.openWith !== ""
            placeholder: "Message @" + root.openWith
            onAccepted: {
                if (text.trim() !== "") { XD.send(root.openWith, text); text = ""; }
            }
        }
    }

    // A text box in the desk's own clothes; QtQuick's own is a different app.
    component Field: Rectangle {
        id: field
        property alias text: input.text
        property string placeholder: ""
        property bool secret: false
        signal accepted()
        height: 34
        radius: 17
        color: Theme.c.surfaceContainerHighest
        border.width: input.activeFocus ? 1 : 0
        border.color: Theme.c.primary
        TextInput {
            id: input
            anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 13
            font.family: Theme.font
            color: Theme.c.onSurface
            echoMode: field.secret ? TextInput.Password : TextInput.Normal
            selectByMouse: true
            onAccepted: field.accepted()
        }
        UText {
            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
            visible: input.text === "" && !input.activeFocus
            text: field.placeholder
            size: 12.5
            color: Theme.c.onSurfaceVariant
        }
    }
}
