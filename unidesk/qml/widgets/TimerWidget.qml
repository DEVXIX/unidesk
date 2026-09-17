import QtQuick
import QtQuick.Shapes
import "../components"
import "../Icons.js" as Icons

// Timer / Pomodoro: a ring that empties as time runs out. Presets, scroll on
// the time to adjust, and at the end a notification (and optionally your music
// pauses). With pomodoro on, focus and break sessions alternate.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real size: opt("size", 230)
    readonly property bool pomodoro: opt("pomodoro", true)
    readonly property int focusMin: opt("focus_minutes", 25)
    readonly property int breakMin: opt("break_minutes", 5)

    property int total: focusMin * 60
    property int remaining: total
    property bool running: false
    property bool onBreak: false
    property real endsAt: 0

    function fmt(s) { var m = Math.floor(s / 60), r = s % 60; return m + ":" + (r < 10 ? "0" : "") + r; }
    function setMinutes(m) { running = false; onBreak = false; total = Math.max(60, m * 60); remaining = total; }
    function toggle() {
        if (running) { running = false; }
        else { if (remaining <= 0) remaining = total; endsAt = Date.now() + remaining * 1000; running = true; }
    }
    function finished() {
        running = false;
        Desk.notify(onBreak ? "Break's over" : "Time's up", onBreak ? "Back to it." : (pomodoro ? "Take a " + breakMin + " minute break." : "Your timer finished."));
        if (root.opt("pause_music", false) && Media.playing && Media.playing.status === "playing") Media.playPause();
        if (pomodoro) {
            onBreak = !onBreak;
            total = (onBreak ? breakMin : focusMin) * 60;
            remaining = total;
            if (root.opt("auto_continue", false)) toggle();
        } else {
            remaining = 0;
        }
    }

    Timer {
        interval: 250
        repeat: true
        running: root.running
        onTriggered: {
            root.remaining = Math.max(0, Math.round((root.endsAt - Date.now()) / 1000));
            if (root.remaining <= 0) root.finished();
        }
    }

    implicitWidth: size
    implicitHeight: size + 56

    Item {
        id: dial
        width: root.size; height: root.size

        MShape { anchors.fill: parent; shape: "cookie12"; color: root.onBreak ? Theme.c.tertiaryContainer : Theme.c.secondaryContainer }

        Shape {
            anchors.fill: parent
            anchors.margins: root.size * 0.12
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Qt.alpha(root.onBreak ? Theme.c.onTertiaryContainer : Theme.c.onSecondaryContainer, 0.15)
                strokeWidth: root.size * 0.05; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: dial.width * 0.38; centerY: dial.height * 0.38; radiusX: dial.width * 0.36; radiusY: dial.height * 0.36; startAngle: -90; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: root.onBreak ? Theme.c.tertiary : Theme.c.primary
                strokeWidth: root.size * 0.05; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: dial.width * 0.38; centerY: dial.height * 0.38; radiusX: dial.width * 0.36; radiusY: dial.height * 0.36
                    startAngle: -90; sweepAngle: 360 * (root.total > 0 ? root.remaining / root.total : 0)
                    Behavior on sweepAngle { NumberAnimation { duration: 300 } }
                }
            }
        }

        Column {
            anchors.centerIn: parent
            UText {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.pomodoro ? (root.onBreak ? "Break" : "Focus") : "Timer"
                size: root.size * 0.07; color: root.onBreak ? Theme.c.onTertiaryContainer : Theme.c.onSecondaryContainer; opacity: 0.8
            }
            UText {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.fmt(root.remaining)
                size: root.size * 0.2; weight: Font.DemiBold
                color: root.onBreak ? Theme.c.onTertiaryContainer : Theme.c.onSecondaryContainer
                font.features: { "tnum": 1 }
                MouseArea {
                    anchors.fill: parent
                    enabled: !root.running
                    onWheel: (w) => root.setMinutes(Math.round(root.total / 60) + (w.angleDelta.y > 0 ? 1 : -1))
                }
            }
        }
    }

    Row {
        anchors { horizontalCenter: dial.horizontalCenter; top: dial.bottom; topMargin: 8 }
        spacing: 6
        IconButton {
            icon: Icons.replay; size: 40; iconSize: 20
            color: Theme.c.surfaceContainerHigh
            onClicked: { root.running = false; root.remaining = root.total; }
        }
        IconButton {
            icon: root.running ? Icons.pause : Icons.play_arrow; size: 44; iconSize: 24; fill: 1; shape: "flower"
            color: Theme.c.primary; iconColor: Theme.c.onPrimary
            onClicked: root.toggle()
        }
        Repeater {
            model: root.opt("presets", [5, 25, 50])
            Rectangle {
                required property var modelData
                anchors.verticalCenter: parent.verticalCenter
                width: presetText.implicitWidth + 20; height: 32; radius: 16
                color: Math.round(root.total / 60) === modelData && !root.onBreak ? Theme.c.secondaryContainer : Theme.c.surfaceContainerHigh
                UText { id: presetText; anchors.centerIn: parent; text: modelData + "m"; size: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.setMinutes(modelData) }
            }
        }
    }
}
