import QtQuick
import QtQuick.Shapes
import "components"
import "Icons.js" as Icons

// Places one widget on its screen's desk. In edit mode: drag to move (snaps to
// the grid; let go over another screen to move it there), drag the corner
// handle to resize, and buttons to customize or remove it. Position and size
// are saved on release, relative to the nearest corner, edge or the centre,
// so the widget keeps its place on a screen of another size.
Item {
    id: frame
    property var spec: ({})
    property QtObject slot: null
    readonly property string widgetId: spec.id || ""
    readonly property var types: ({
        time: "Time", clock: "Clock", media: "Media", system: "System", weather: "Weather",
        calendar: "Calendar", profile: "Profile", github: "GitHub", picture: "Picture",
        network: "Network", storage: "Storage", clipboard: "Clipboard", notifications: "Notifications"
    ,
        mixer: "Mixer", notes: "Notes", timer: "Timer", launcher: "Launcher", games: "Games", league: "League",
        countdown: "Countdown", slideshow: "Slideshow", quote: "Quote", dev: "Dev", devices: "Devices",
        xd: "Xd"
    })

    property bool dragging: false
    property bool resizing: false
    property real dragX: 0
    property real dragY: 0
    property real liveScale: 1
    property real resizeX: 0
    property real resizeY: 0
    property bool selected: false

    readonly property real widgetScale: (resizing ? liveScale : (spec.scale || 1)) * Theme.scale
    readonly property real baseWidth: loader.item ? loader.item.width : unknown.width
    readonly property real baseHeight: loader.item ? loader.item.height : unknown.height

    // Where it sits: x / y measured inward from its anchor (layout.py does the reverse).
    readonly property string anchorName: spec.anchor || "top-left"
    readonly property real areaWidth: parent ? parent.width : 0
    readonly property real areaHeight: parent ? parent.height : 0
    readonly property real homeX: /left$/.test(anchorName) ? (spec.x || 0)
                                : /right$/.test(anchorName) ? areaWidth - width - (spec.x || 0)
                                : (areaWidth - width) / 2 + (spec.x || 0)
    readonly property real homeY: /^top/.test(anchorName) ? (spec.y || 0)
                                : /^bottom/.test(anchorName) ? areaHeight - height - (spec.y || 0)
                                : (areaHeight - height) / 2 + (spec.y || 0)
    // Always fully on screen, whatever the resolution.
    function onScreenX(v) { return Math.round(Math.max(0, Math.min(areaWidth - width, v))); }
    function onScreenY(v) { return Math.round(Math.max(0, Math.min(areaHeight - height, v))); }

    function save(extra) {
        var placed = Desk.placeWidget(Object.assign({
            id: frame.widgetId, display: frame.slot ? frame.slot.number : 1, screen: frame.spec.screen || 1,
            left: frame.x, top: frame.y, width: frame.width, height: frame.height, scale: frame.spec.scale || 1
        }, extra || {}));
        // Still shown on this screen: nothing reloads, so keep the saved placement here.
        if (!frame.slot || placed.display === frame.slot.number) frame.spec = Object.assign({}, frame.spec, placed);
    }
    function toggleOptions() { Desk.select(Desk.selected === frame.widgetId ? "" : frame.widgetId); }

    signal geometryMoved()

    x: dragging ? dragX : resizing ? resizeX : onScreenX(homeX)
    y: dragging ? dragY : resizing ? resizeY : onScreenY(homeY)
    width: Math.round(baseWidth * widgetScale)
    height: Math.round(baseHeight * widgetScale)
    z: dragging || resizing ? 10 : selected ? 5 : 0

    onXChanged: geometryMoved()
    onYChanged: geometryMoved()
    onWidthChanged: geometryMoved()
    onHeightChanged: geometryMoved()

    // Left out of the lock screen picture: Windows draws its own clock there,
    // so ours would only be a second one showing when the picture was painted.
    // It is one frame, and the widget is back before anybody sees the desk.
    readonly property bool hiddenOnLock:
        Desk.lockShot && Desk.lockHidden.indexOf(String(frame.spec.type)) >= 0

    Item {
        id: content
        visible: !frame.hiddenOnLock
        width: frame.baseWidth
        height: frame.baseHeight
        transform: Scale { xScale: frame.widgetScale; yScale: frame.widgetScale }
        opacity: 0
        Component.onCompleted: opacity = 1
        Behavior on opacity { NumberAnimation { duration: 450 * Theme.animationSpeed; easing.type: Easing.OutCubic } }

        Loader {
            id: loader
            source: frame.types[frame.spec.type] ? "widgets/" + frame.types[frame.spec.type] + "Widget.qml" : ""
            onLoaded: {
                item.options = Qt.binding(() => frame.spec.options || {});
                if (item.hasOwnProperty("widgetId")) item.widgetId = Qt.binding(() => frame.widgetId);
            }
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
                property point grab
                property real startX
                property real startY
                function snap(v) { return Desk.grid > 0 ? Math.round(v / Desk.grid) * Desk.grid : Math.round(v); }
                onPressed: (e) => {
                    start = mapToItem(frame.parent, e.x, e.y);
                    grab = mapToItem(frame, e.x, e.y);
                    startX = frame.x; startY = frame.y;
                    frame.dragX = startX; frame.dragY = startY;
                    frame.dragging = true;
                }
                onPositionChanged: (e) => {
                    if (!pressed) return;
                    var p = mapToItem(frame.parent, e.x, e.y);
                    frame.dragX = Math.max(0, Math.min(frame.areaWidth - frame.width, snap(startX + p.x - start.x)));
                    frame.dragY = Math.max(0, Math.min(frame.areaHeight - frame.height, snap(startY + p.y - start.y)));
                }
                onReleased: (e) => {
                    var cursor = mapToGlobal(e.x, e.y);
                    var over = Desk.screenAt(cursor.x, cursor.y);
                    var elsewhere = over > 0 && frame.slot && over !== frame.slot.number;
                    var moved = elsewhere || frame.dragX !== startX || frame.dragY !== startY;
                    if (moved) frame.save({ left: frame.dragX, top: frame.dragY, cursorX: cursor.x, cursorY: cursor.y, grabX: grab.x, grabY: grab.y });
                    frame.dragging = false;
                    if (!moved) frame.toggleOptions();   // a plain click opens its options
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
                    onClicked: frame.toggleOptions()
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
                        // The top-left corner stays put while resizing, whatever the anchor.
                        frame.resizeX = frame.x;
                        frame.resizeY = frame.y;
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
                        frame.save({ scale: frame.liveScale, anchor: frame.anchorName });  // resizing keeps the anchor it has
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
            Desk.select(frame.widgetId);
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
