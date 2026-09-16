import QtQuick
import QtQuick.Effects
import "../components"

// Just the day and the time, straight on the wallpaper.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real size: opt("size", 150)
    readonly property bool h12: opt("format", "24h") === "12h"
    readonly property bool seconds: opt("seconds", false)
    property date now: new Date()

    implicitWidth: Math.max(timeText.implicitWidth, dayText.implicitWidth) + 8
    implicitHeight: column.implicitHeight

    // Wake once a minute (on the minute), or every second with seconds on.
    Timer {
        running: true
        repeat: false
        interval: root.seconds ? 1000 - new Date().getMilliseconds() : 60000 - (new Date().getSeconds() * 1000 + new Date().getMilliseconds())
        onTriggered: { root.now = new Date(); restart(); }
    }

    Column {
        id: column
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: -root.size * 0.12
        layer.enabled: Theme.shadows
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, 0.55)
            shadowBlur: 0.6
            shadowVerticalOffset: 3
        }

        UText {
            id: dayText
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatDate(root.now, "dddd")
            size: root.size * 0.24
            weight: Font.Medium
            color: Theme.c.primaryFixed
            font.letterSpacing: root.size * 0.004
        }
        UText {
            id: timeText
            anchors.horizontalCenter: parent.horizontalCenter
            // Qt only uses 12-hour "h" when AP is in the same pattern, so build it by hand.
            text: (root.h12 ? String(root.now.getHours() % 12 || 12) : Qt.formatTime(root.now, "HH"))
                  + Qt.formatTime(root.now, root.seconds ? ":mm:ss" : ":mm")
            size: root.size
            weight: Font.DemiBold
            color: Theme.dark ? "#ffffff" : Theme.c.onSurface
            font.letterSpacing: -root.size * 0.03
            font.features: { "tnum": 1 }
        }
        UText {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.opt("date", true)
            topPadding: root.size * 0.08
            text: Qt.formatDate(root.now, "d MMMM") + (root.h12 ? "  ·  " + Qt.formatTime(root.now, "AP") : "")
            size: root.size * 0.13
            color: Theme.c.primaryFixedDim
        }
    }
}
