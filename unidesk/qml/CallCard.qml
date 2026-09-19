import QtQuick
import "components"
import "Icons.js" as Icons

// The call, in the bottom right corner.
//
// The window stands still; this slides up inside it. It is the same card for
// all three states a call has - ringing at you, ringing at somebody else, and
// under way - because they are the same call and watching it change is how you
// follow what is happening.
Item {
    id: root
    anchors.fill: parent

    readonly property var call: Calls.call || ({})
    readonly property bool incoming: Calls.isRinging
    readonly property bool outgoing: Calls.isOutgoing
    readonly property bool talking: false   // answered calls live in the widget

    Card {
        id: card
        width: parent.width - 16
        height: 158
        x: 8
        tone: "high"

        // Bound, not assigned. Assigning the resting place in
        // Component.onCompleted read parent.height before the view had sized
        // the root item - so the card settled at a negative y and the whole
        // thing was a blank window. A binding re-reads the height when it
        // arrives, and animates there through the Behavior below.
        property bool arrived: false
        y: arrived ? parent.height - height - 8 : parent.height
        Component.onCompleted: arrived = true
        Behavior on y {
            NumberAnimation {
                duration: 420
                easing.type: Easing.OutBack
                easing.overshoot: 0.7
            }
        }

        // ---- who ------------------------------------------------------------------
        Item {
            id: face
            width: 54
            height: 54
            anchors { left: parent.left; leftMargin: 14; top: parent.top; topMargin: 14 }

            // The sound made visible, for anyone with the volume down.
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + 10
                height: width
                radius: width / 2
                color: Theme.c.primary
                opacity: 0
                visible: root.incoming || root.outgoing
                SequentialAnimation on opacity {
                    running: root.incoming || root.outgoing
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.34; to: 0; duration: 1500; easing.type: Easing.OutCubic }
                }
                scale: root.incoming || root.outgoing ? 1.3 : 1
                Behavior on scale { NumberAnimation { duration: 1500 } }
            }

            ShapedImage {
                anchors.fill: parent
                source: root.call.avatar || ""
                shape: "cookie"
                visible: (root.call.avatar || "") !== ""
            }
            MShape {
                anchors.fill: parent
                shape: "cookie"
                color: Theme.c.surfaceContainerHighest
                visible: (root.call.avatar || "") === ""
            }
            UText {
                anchors.centerIn: parent
                visible: (root.call.avatar || "") === ""
                text: (root.call.name || "?").charAt(0).toUpperCase()
                size: 22; weight: Font.Medium
            }
        }

        Column {
            anchors {
                left: face.right; leftMargin: 12; right: parent.right; rightMargin: 14
                top: parent.top; topMargin: 18
            }
            spacing: 2

            UText {
                width: parent.width
                text: root.call.name || "someone"
                size: 15; weight: Font.Medium; elide: Text.ElideRight
            }
            UText {
                width: parent.width
                visible: (root.call.handle || "") !== ""
                text: "@" + (root.call.handle || "")
                size: 11.5; color: Theme.c.onSurfaceVariant; elide: Text.ElideRight
            }
            UText {
                width: parent.width
                text: root.incoming ? (root.call.isGroup ? "Incoming group call…" : "Incoming call…")
                    : "Ringing…"
                size: 12
                color: Theme.c.onSurfaceVariant
                topPadding: 4
            }
        }

        // ---- what you can do about it ---------------------------------------------
        Row {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 16 }
            spacing: root.incoming ? 26 : 14

            // Decline, or hang up: the red one is always the way out.
            Rectangle {
                width: 46; height: 46; radius: 23
                color: "#d9463c"
                MIcon { anchors.centerIn: parent; icon: Icons.call_end; size: 20; color: "#ffffff" }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.incoming ? Calls.decline() : Calls.hangUp()
                }
            }

            // Mute, once there is something to mute.
            Rectangle {
                visible: root.talking
                width: 46; height: 46; radius: 23
                color: Calls.muted ? Theme.c.surfaceContainerHighest : Theme.c.primaryContainer
                MIcon {
                    anchors.centerIn: parent
                    icon: Calls.muted ? Icons.mic_off : Icons.mic
                    size: 19
                    color: Calls.muted ? Theme.c.onSurfaceVariant : Theme.c.onPrimaryContainer
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Calls.toggleMute()
                }
            }

            // Answer.
            Rectangle {
                visible: root.incoming
                width: 46; height: 46; radius: 23
                color: "#35b46a"
                MIcon { anchors.centerIn: parent; icon: Icons.call; size: 20; color: "#ffffff" }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Calls.answer()
                }
            }
        }

        // Anything the server refused, said where it happened rather than in a log.
        UText {
            anchors { left: parent.left; right: parent.right; margins: 14; bottom: parent.bottom; bottomMargin: 2 }
            visible: Calls.error !== ""
            text: Calls.error
            size: 10.5; color: Theme.c.error
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }
}
