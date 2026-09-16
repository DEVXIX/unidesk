import QtQuick
import QtQuick.Effects
import "../components"
import "../Icons.js" as Icons

// You, the machine, the weather in a word, and lock / settings / power.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property var s: System.stats
    readonly property string avatarOpt: String(opt("avatar", "github"))
    readonly property string bgOpt: String(opt("background", "wallpaper"))
    property bool powerOpen: false
    property string armed: ""

    function uptime(sec) {
        var m = Math.floor(sec / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
        if (d > 0) return d + "d " + (h % 24) + "h";
        if (h > 0) return h + "h " + (m % 60) + "m";
        return m + "m";
    }
    function imageFor(value) {
        if (value === "wallpaper") return Desk.wallpaper;
        if (value === "artwork") return Media.playing && Media.playing.art ? Media.playing.art : Desk.wallpaper;
        if (value === "github") return GitHub.data ? GitHub.data.avatar : "";
        return Desk.fileUrl(value);
    }

    implicitWidth: opt("width", 280)
    implicitHeight: 250

    RectangularShadow {
        anchors.fill: parent
        visible: Theme.shadows
        radius: Theme.radius
        blur: 20; spread: -2; offset.y: 4
        color: Qt.rgba(0, 0, 0, 0.3)
    }

    // background picture, rounded
    Item {
        anchors.fill: parent
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true; maskSource: bgMask
            maskThresholdMin: 0.5; maskSpreadAtMin: 1.0
        }
        Rectangle { anchors.fill: parent; color: Theme.c.surfaceContainerHigh }
        Image {
            id: bgImage
            anchors.fill: parent
            source: root.imageFor(root.bgOpt)
            fillMode: Image.PreserveAspectCrop
            sourceSize: Qt.size(root.width, root.height)
            asynchronous: true
            visible: false
        }
        MultiEffect {
            anchors.fill: parent
            source: bgImage
            blurEnabled: true; blur: 0.5; blurMax: 32
            visible: bgImage.status === Image.Ready
        }
    }
    Rectangle { id: bgMask; anchors.fill: parent; radius: Theme.radius; visible: false; layer.enabled: true }

    Card {
        id: panel
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 14 }
        height: 160
        radius: Theme.radius - 8

        ShapedImage {
            id: avatar
            x: 14; y: -30
            width: 72; height: 72
            shape: "circle"
            source: root.imageFor(root.avatarOpt)
        }
        Column {
            anchors { left: avatar.right; leftMargin: 12; right: parent.right; rightMargin: 12; top: parent.top; topMargin: 8 }
            UText { width: parent.width; text: root.s.user + "@" + root.s.host.toLowerCase(); size: 15; weight: Font.Medium }
            UText { text: "Up • " + root.uptime(root.s.uptime); size: 11.5; color: Theme.c.onSurfaceVariant }
        }

        Row {
            x: 14; y: 56
            spacing: 6
            visible: !root.powerOpen
            MIcon { icon: Weather.data ? Icons.cloud : Icons.schedule; size: 16; color: Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
            UText {
                anchors.verticalCenter: parent.verticalCenter
                text: Weather.data ? "• " + Weather.data.summary : "• " + Qt.formatDate(new Date(), "dddd")
                size: 14
            }
        }

        Row {
            anchors { left: parent.left; leftMargin: 14; bottom: parent.bottom; bottomMargin: 14 }
            spacing: 8
            visible: !root.powerOpen

            Rectangle {
                width: 112; height: 42; radius: 21
                color: Theme.c.primary
                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    MIcon { icon: Icons.lock; size: 18; fill: 1; color: Theme.c.onPrimary; anchors.verticalCenter: parent.verticalCenter }
                    UText { text: "Lock"; size: 15; weight: Font.Medium; color: Theme.c.onPrimary; anchors.verticalCenter: parent.verticalCenter }
                }
                Rectangle {
                    anchors.fill: parent; radius: parent.radius; color: Theme.c.onPrimary
                    opacity: lockMouse.pressed ? 0.16 : lockMouse.containsMouse ? 0.08 : 0
                }
                MouseArea { id: lockMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Desk.systemAction("lock") }
            }
            IconButton { icon: Icons.settings; size: 42; outlined: true; onClicked: Desk.systemAction("settings") }
            IconButton { icon: Icons.power_settings_new; size: 42; outlined: true; onClicked: { root.powerOpen = true; root.armed = ""; } }
        }

        // power menu: tap an action, tap it again to confirm
        Grid {
            visible: root.powerOpen
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
            columns: 2
            rowSpacing: 6; columnSpacing: 6
            Repeater {
                model: [["sleep", Icons.bedtime, "Sleep"], ["restart", Icons.restart_alt, "Restart"], ["shutdown", Icons.power_settings_new, "Shut down"], ["signout", Icons.logout, "Sign out"]]
                Rectangle {
                    required property var modelData
                    readonly property bool isArmed: root.armed === modelData[0]
                    width: (panel.width - 30) / 2; height: 40; radius: 14
                    color: isArmed ? Theme.c.error : Theme.c.surfaceContainerHighest
                    Behavior on color { ColorAnimation { duration: 200 } }
                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        MIcon { icon: modelData[1]; size: 17; color: isArmed ? Theme.c.onError : Theme.c.onSurface; anchors.verticalCenter: parent.verticalCenter }
                        UText { text: isArmed ? "Sure?" : modelData[2]; size: 13; weight: Font.Medium; color: isArmed ? Theme.c.onError : Theme.c.onSurface; anchors.verticalCenter: parent.verticalCenter }
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (isArmed) { root.powerOpen = false; Desk.systemAction(modelData[0]); }
                            else root.armed = modelData[0];
                        }
                    }
                }
            }
        }
        IconButton {
            visible: root.powerOpen
            anchors { right: parent.right; top: parent.top; margins: 8 }
            icon: Icons.close; size: 30
            onClicked: root.powerOpen = false
        }
        Timer { running: root.powerOpen; interval: 8000; onTriggered: root.powerOpen = false }
    }
}
