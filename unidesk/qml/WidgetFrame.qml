import QtQuick
import QtQuick.Shapes
import "components"
import "Icons.js" as Icons

// Places one widget on the desk. In edit mode: drag to move (snaps to the
// grid), drag the corner handle to resize, and buttons to customize or
// remove it. Position and size are saved on release.
Item {
    id: frame
    property var spec: ({})
    readonly property string widgetId: spec.id || ""
    readonly property var types: ({
        time: "Time", clock: "Clock", media: "Media", system: "System", weather: "Weather",
        calendar: "Calendar", profile: "Profile", github: "GitHub", picture: "Picture"
    })

    property bool dragging: false
    property bool resizing: false
    property real dragX: 0
    property real dragY: 0
    property real liveScale: 1
    property bool selected: false

    readonly property real widgetScale: (resizing ? liveScale : (spec.scale || 1)) * Theme.scale
    readonly property real baseWidth: loader.item ? loader.item.width : unknown.width
    readonly property real baseHeight: loader.item ? loader.item.height : unknown.height

    signal customize()
    signal geometryMoved()

    x: dragging ? dragX : spec.x
    y: dragging ? dragY : spec.y
    width: Math.round(baseWidth * widgetScale)
    height: Math.round(baseHeight * widgetScale)
    z: dragging || resizing ? 10 : selected ? 5 : 0

    onXChanged: geometryMoved()
    onYChanged: geometryMoved()
    onWidthChanged: geometryMoved()
    onHeightChanged: geometryMoved()

    Item {
        id: content
        width: frame.baseWidth
        height: frame.baseHeight
        transform: Scale { xScale: frame.widgetScale; yScale: frame.widgetScale }
        opacity: 0
        Component.onCompleted: opacity = 1
        Behavior on opacity { NumberAnimation { duration: 450 * Theme.animationSpeed; easing.type: Easing.OutCubic } }

        Loader {
            id: loader
            source: frame.types[frame.spec.type] ? "widgets/" + frame.types[frame.spec.type] + "Widget.qml" : ""
            onLoaded: item.options = Qt.binding(() => frame.spec.options || {})
        }

        Card {
            id: unknown
            visible: !loader.item
            width: 300; height: 64
            UText {
                anchors.centerIn: parent
                width: parent.width - 24
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                text: loader.status === Loader.Error ? "'" + frame.spec.type + "' widget failed to load" : "Unknown widget type '" + frame.spec.type + "'"
                color: Theme.c.error
            }
        }
    }

    // ---- edit mode -------------------------------------------------------------
    Loader {
        active: Desk.editing
        anchors.fill: parent
        sourceComponent: Item {
            Shape {
                x: -6; y: -6
                width: frame.width + 12; height: frame.height + 12
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: Theme.c.primary
                    strokeWidth: frame.selected ? 2.5 : 2
                    strokeStyle: frame.selected ? ShapePath.SolidLine : ShapePath.DashLine
                    dashPattern: [4, 3]
                    fillColor: Qt.alpha(Theme.c.primary, frame.dragging || frame.resizing ? 0.12 : 0.05)
                    PathRectangle { x: 1; y: 1; width: frame.width + 10; height: frame.height + 10; radius: Math.min(Theme.radius + 4, (frame.height + 10) / 2) }
                }
            }

            // drag anywhere on the widget
            MouseArea {
                anchors.fill: parent
                anchors.margins: -6
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property point start
                property real startX
                property real startY
                function snap(v) { return Desk.grid > 0 ? Math.round(v / Desk.grid) * Desk.grid : Math.round(v); }
                onPressed: (e) => {
                    start = mapToItem(frame.parent, e.x, e.y);
                    startX = frame.spec.x; startY = frame.spec.y;
                    frame.dragX = startX; frame.dragY = startY;
                    frame.dragging = true;
                }
                onPositionChanged: (e) => {
                    if (!pressed) return;
                    var p = mapToItem(frame.parent, e.x, e.y);
                    frame.dragX = Math.max(0, Math.min(frame.parent.width - frame.width, snap(startX + p.x - start.x)));
                    frame.dragY = Math.max(0, Math.min(frame.parent.height - frame.height, snap(startY + p.y - start.y)));
                }
                onReleased: {
                    var moved = frame.dragX !== frame.spec.x || frame.dragY !== frame.spec.y;
                    if (moved) {
                        Desk.placeWidget(frame.widgetId, frame.dragX, frame.dragY, frame.spec.scale || 1);
                        frame.spec = Object.assign({}, frame.spec, { x: frame.dragX, y: frame.dragY });
                    }
                    frame.dragging = false;
                    if (!moved) frame.customize();   // a plain click opens its options
                }
            }

            // id label
            Rectangle {
                x: 10; y: -17
                height: 24; radius: 12
                width: idLabel.implicitWidth + 32
                color: Theme.c.primary
                Row {
                    anchors.centerIn: parent
                    spacing: 4
                    MIcon { icon: Icons.open_with; size: 14; color: Theme.c.onPrimary; anchors.verticalCenter: parent.verticalCenter }
                    UText { id: idLabel; text: frame.widgetId; size: 12; weight: Font.Medium; color: Theme.c.onPrimary; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            // customize / remove
            Row {
                anchors { right: parent.right; rightMargin: 8; top: parent.top; topMargin: -18 }
                spacing: 6
                IconButton {
                    icon: Icons.tune; size: 34; iconSize: 19
                    color: Theme.c.primaryContainer; iconColor: Theme.c.onPrimaryContainer
                    onClicked: frame.customize()
                }
                IconButton {
                    id: removeButton
                    property bool armed: false
                    icon: armed ? Icons.check : Icons.delete_; size: 34; iconSize: 19
                    color: armed ? Theme.c.error : Theme.c.errorContainer
                    iconColor: armed ? Theme.c.onError : Theme.c.onErrorContainer
                    onClicked: armed ? Desk.removeWidget(frame.widgetId) : armed = true
                    Timer { running: removeButton.armed; interval: 2500; onTriggered: removeButton.armed = false }
                }
            }

            // resize handle (bottom-right corner)
            Rectangle {
                id: handle
                x: frame.width - width / 2 - 2
                y: frame.height - height / 2 - 2
                width: 26; height: 26; radius: 13
                color: Theme.c.primary
                border.width: 3
                border.color: Theme.c.surface
                MIcon { anchors.centerIn: parent; icon: Icons.open_in_full; size: 14; color: Theme.c.onPrimary; rotation: 90 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.SizeFDiagCursor
                    preventStealing: true
                    property point start
                    property real startScale
                    property real startSpan
                    onPressed: (e) => {
                        start = mapToItem(frame.parent, e.x, e.y);
                        startScale = frame.spec.scale || 1;
                        startSpan = Math.max(40, frame.width + frame.height);
                        frame.liveScale = startScale;
                        frame.resizing = true;
                    }
                    onPositionChanged: (e) => {
                        if (!pressed) return;
                        var p = mapToItem(frame.parent, e.x, e.y);
                        var grow = (p.x - start.x) + (p.y - start.y);
                        var s = startScale * (startSpan + grow) / startSpan;
                        frame.liveScale = Math.max(0.4, Math.min(3, Math.round(s * 20) / 20));
                    }
                    onReleased: {
                        Desk.placeWidget(frame.widgetId, frame.spec.x, frame.spec.y, frame.liveScale);
                        frame.spec = Object.assign({}, frame.spec, { scale: frame.liveScale });
                        frame.resizing = false;
                    }
                }
            }
        }
    }

    // Right-click anywhere on a widget: open its options (switching on edit mode).
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        z: 20
        onClicked: {
            if (!Desk.editing) Desk.setEditing(true);
            frame.customize();
        }
    }

    // size read-out while resizing
    Rectangle {
        visible: frame.resizing
        anchors.centerIn: parent
        width: sizeText.implicitWidth + 24; height: 34; radius: 17
        color: Theme.c.inverseSurface
        UText { id: sizeText; anchors.centerIn: parent; text: Math.round(frame.liveScale * 100) + "%"; size: 15; weight: Font.Medium; color: Theme.c.inverseOnSurface }
    }
}
