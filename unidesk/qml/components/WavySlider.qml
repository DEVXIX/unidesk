import QtQuick
import QtQuick.Shapes
import "../Shapes.js" as Shapes

// Material 3 expressive seek bar: a wave for the played part, a flat line
// for the rest, a pill thumb. Drag or click to seek.
Item {
    id: root
    property real value: 0          // 0..1
    property bool playing: false
    property real phase: 0          // advance this to make the wave drift
    property color activeColor: Theme.c.primary
    property color trackColor: Theme.c.outlineVariant
    signal seek(real fraction)

    implicitHeight: 24

    readonly property real shown: mouse.pressed ? mouse.preview : Math.max(0, Math.min(1, value))
    readonly property real thumbX: Math.round(shown * width)
    property real amp: playing ? 3 : 0.01
    Behavior on amp { NumberAnimation { duration: 400 } }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.activeColor
            strokeWidth: 3.5
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            fillColor: "transparent"
            PathSvg { path: Shapes.wave(3, Math.max(3, root.thumbX - 7), root.height / 2, root.amp, 22, root.phase) }
        }
        ShapePath {
            strokeColor: root.trackColor
            strokeWidth: 3.5
            capStyle: ShapePath.RoundCap
            fillColor: "transparent"
            startX: Math.min(root.width - 3, root.thumbX + 7); startY: root.height / 2
            PathLine { x: root.width - 3; y: root.height / 2 }
        }
    }

    Rectangle {
        x: root.thumbX - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: 4
        height: mouse.pressed ? 22 : 18
        radius: 2
        color: root.activeColor
        Behavior on height { NumberAnimation { duration: 150 } }
    }

    MouseArea {
        id: mouse
        property real preview: 0
        anchors.fill: parent
        anchors.margins: -6
        cursorShape: Qt.PointingHandCursor
        preventStealing: true
        function at(x) { return Math.max(0, Math.min(1, (x - 6) / root.width)); }
        onPressed: (e) => preview = at(e.x)
        onPositionChanged: (e) => { if (pressed) preview = at(e.x); }
        onReleased: root.seek(preview)
    }
}
