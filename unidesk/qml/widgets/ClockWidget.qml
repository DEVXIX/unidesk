import QtQuick
import "../components"
import "../Icons.js" as Icons

// Analog clock on a cookie shape: faint numerals, rounded hands, an orbiting
// seconds dot, hour and minute badges, and an optional quote pill.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real size: opt("size", 240)
    readonly property bool seconds: opt("seconds", true)
    readonly property string quote: opt("quote", "")
    property date now: new Date()

    implicitWidth: size
    implicitHeight: size + (quote ? 46 : 0)

    Timer {
        running: true
        repeat: false
        interval: root.seconds ? 1000 - new Date().getMilliseconds() : 60000 - (new Date().getSeconds() * 1000 + new Date().getMilliseconds())
        onTriggered: { root.now = new Date(); restart(); }
    }

    Item {
        id: face
        width: root.size
        height: root.size
        readonly property real c: width / 2

        MShape {
            anchors.fill: parent
            shape: "cookie"
            color: Theme.c.secondaryContainer
        }

        Repeater {
            model: [["12", 0.5, 0.2], ["3", 0.8, 0.5], ["6", 0.5, 0.8], ["9", 0.2, 0.5]]
            UText {
                required property var modelData
                x: face.width * modelData[1] - width / 2
                y: face.height * modelData[2] - height / 2
                text: modelData[0]
                size: root.size * 0.25
                weight: Font.Bold
                color: Theme.c.onSecondaryContainer
                opacity: 0.16
            }
        }

        // hour hand
        Rectangle {
            readonly property real len: root.size * 0.26
            width: root.size * 0.07
            height: len + width
            radius: width / 2
            x: face.c - width / 2
            y: face.c - len - width / 2
            color: Theme.c.tertiary
            antialiasing: true
            transform: Rotation {
                origin.x: root.size * 0.035
                origin.y: root.size * 0.26 + root.size * 0.035
                angle: (root.now.getHours() % 12 + root.now.getMinutes() / 60) * 30
                Behavior on angle { RotationAnimation { duration: 600; direction: RotationAnimation.Clockwise; easing.type: Easing.OutBack } }
            }
        }
        // minute hand
        Rectangle {
            readonly property real len: root.size * 0.34
            width: root.size * 0.055
            height: len + width
            radius: width / 2
            x: face.c - width / 2
            y: face.c - len - width / 2
            color: Theme.c.primary
            antialiasing: true
            transform: Rotation {
                origin.x: root.size * 0.0275
                origin.y: root.size * 0.34 + root.size * 0.0275
                angle: root.now.getMinutes() * 6
                Behavior on angle { RotationAnimation { duration: 600; direction: RotationAnimation.Clockwise; easing.type: Easing.OutBack } }
            }
        }
        // seconds dot
        Rectangle {
            visible: root.seconds
            readonly property real a: root.now.getSeconds() * 6 * Math.PI / 180
            width: root.size * 0.06
            height: width
            radius: width / 2
            color: Theme.c.primary
            x: face.c + Math.sin(a) * root.size * 0.3 - width / 2
            y: face.c - Math.cos(a) * root.size * 0.3 - height / 2
        }
        Rectangle {
            width: root.size * 0.05; height: width; radius: width / 2
            x: face.c - width / 2; y: face.c - height / 2
            color: Theme.c.onSecondaryContainer
        }

        // hour badge
        Item {
            x: root.size * 0.02; y: root.size * 0.02
            width: root.size * 0.25; height: width
            MShape { anchors.fill: parent; shape: "pentagon"; color: Theme.c.tertiaryContainer }
            UText {
                anchors.centerIn: parent
                text: String(root.now.getHours() % 12 || 12)
                size: root.size * 0.12; weight: Font.Bold
                color: Theme.c.onTertiaryContainer
            }
        }
        // minute badge
        Rectangle {
            x: root.size * 0.72; y: root.size * 0.72
            width: root.size * 0.25; height: width; radius: width / 2
            color: Theme.c.surfaceContainerHighest
            UText {
                anchors.centerIn: parent
                text: Qt.formatTime(root.now, "mm")
                size: root.size * 0.12; weight: Font.Bold
                color: Theme.c.onSurface
            }
        }
    }

    Rectangle {
        visible: root.quote !== ""
        anchors.horizontalCenter: face.horizontalCenter
        y: face.height + 10
        height: 34
        width: quoteRow.implicitWidth + 24
        radius: 12
        color: Theme.c.surfaceContainerHigh
        Row {
            id: quoteRow
            anchors.centerIn: parent
            spacing: 6
            MIcon { icon: Icons.format_quote; size: 18; fill: 1; color: Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
            UText { text: root.quote; size: 15; weight: Font.Medium; anchors.verticalCenter: parent.verticalCenter }
        }
    }
}
