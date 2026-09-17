import QtQuick
import "../components"
import "../Icons.js" as Icons

// Days until a date, as a big number on an expressive shape.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real size: opt("size", 210)
    readonly property string label: opt("label", "New Year")
    readonly property date target: {
        var raw = String(opt("date", (new Date().getFullYear() + 1) + "-01-01"));
        var parts = raw.split(/[-/.]/).map(Number);
        return parts.length >= 3 ? new Date(parts[0], parts[1] - 1, parts[2]) : new Date(raw);
    }
    property date now: new Date()
    Timer { interval: 60000; running: true; repeat: true; onTriggered: root.now = new Date() }

    readonly property real msLeft: target.getTime() - now.getTime()
    readonly property int days: Math.ceil(msLeft / 86400000)
    readonly property bool today: days === 0 || (msLeft <= 0 && msLeft > -86400000)
    readonly property bool past: msLeft <= -86400000

    implicitWidth: size
    implicitHeight: size + 34

    Item {
        id: shape
        width: root.size; height: root.size
        MShape {
            anchors.fill: parent
            shape: root.opt("shape", "burst")
            color: root.today ? Theme.c.primary : Theme.c.tertiaryContainer
            rotation: root.today ? 360 : 0
            Behavior on rotation { NumberAnimation { duration: 1200; easing.type: Easing.OutBack } }
        }
        Column {
            anchors.centerIn: parent
            MIcon {
                visible: root.today
                anchors.horizontalCenter: parent.horizontalCenter
                icon: Icons.celebration; size: root.size * 0.28; fill: 1
                color: Theme.c.onPrimary
            }
            UText {
                visible: !root.today
                anchors.horizontalCenter: parent.horizontalCenter
                text: Math.abs(root.days)
                size: root.size * (Math.abs(root.days) > 999 ? 0.22 : 0.3)
                weight: Font.Bold
                color: Theme.c.onTertiaryContainer
                font.features: { "tnum": 1 }
            }
            UText {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.today ? "Today!" : (Math.abs(root.days) === 1 ? "day" : "days") + (root.past ? " ago" : " to go")
                size: root.size * 0.075
                color: root.today ? Theme.c.onPrimary : Theme.c.onTertiaryContainer
            }
        }
    }
    Rectangle {
        anchors { horizontalCenter: shape.horizontalCenter; top: shape.bottom; topMargin: 2 }
        height: 30; radius: 15; width: labelText.implicitWidth + 26
        color: Theme.c.surfaceContainerHigh
        UText {
            id: labelText
            anchors.centerIn: parent
            text: root.label + "  ·  " + Qt.formatDate(root.target, "d MMM yyyy")
            size: 13; weight: Font.Medium
        }
    }
}
