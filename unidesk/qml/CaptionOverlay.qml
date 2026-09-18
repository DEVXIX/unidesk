import QtQuick
import "components"

// The cookie caption buttons. Hosted in a QQuickView positioned by
// captionbuttons.py exactly over the active window's real buttons.
Item {
    id: root
    readonly property var kinds: {
        var out = [];
        if (Caption.hasMin) out.push("min");
        if (Caption.hasMax) out.push("max");
        out.push("close");
        return out;
    }

    // Cover DWM's real buttons with the dock clock's colour, so the strip
    // reads as the same accent pill.
    Rectangle { anchors.fill: parent; color: Theme.c.primaryContainer }

    Row {
        anchors.fill: parent
        Repeater {
            model: root.kinds
            delegate: Item {
                id: cell
                required property string modelData
                width: root.width / root.kinds.length
                height: root.height
                readonly property bool isClose: modelData === "close"

                // cookie badge on hover / press (variant C: soft 12-bump, bigger)
                MShape {
                    anchors.centerIn: parent
                    readonly property real base: Math.min(cell.width, cell.height) * 0.78
                    width: base; height: base
                    visible: hover.hovered
                    shape: "cookie12"
                    color: cell.isClose ? Theme.c.error : Theme.c.primary
                    scale: press.pressed ? 1.14 : 1.0
                    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                }

                // Glyph, drawn from primitives so it stays crisp at any scale.
                Item {
                    anchors.centerIn: parent
                    readonly property real g: Math.round(Math.min(cell.width, cell.height) * 0.30)
                    width: g; height: g
                    readonly property color ink: hover.hovered
                        ? (cell.isClose ? Theme.c.onError : "#12233d")
                        : Theme.c.onPrimaryContainer
                    readonly property real t: Math.max(1.4, g * 0.11)

                    Rectangle {  // minimize
                        visible: cell.modelData === "min"
                        anchors.centerIn: parent
                        width: parent.width; height: parent.t; radius: height / 2
                        color: parent.ink
                    }
                    Rectangle {  // maximize
                        visible: cell.modelData === "max" && !Caption.maximized
                        anchors.centerIn: parent
                        width: parent.width; height: parent.height; radius: parent.t
                        color: "transparent"; border.width: parent.t; border.color: parent.ink
                    }
                    Item {  // restore (two offset squares)
                        visible: cell.modelData === "max" && Caption.maximized
                        anchors.fill: parent
                        Rectangle {
                            x: parent.width * 0.22; y: 0; width: parent.width * 0.78; height: parent.height * 0.78
                            radius: parent.parent.t; color: "transparent"; border.width: parent.parent.t; border.color: parent.parent.ink
                        }
                        Rectangle {
                            x: 0; y: parent.height * 0.22; width: parent.width * 0.78; height: parent.height * 0.78
                            radius: parent.parent.t; color: Theme.c.primaryContainer
                            border.width: parent.parent.t; border.color: parent.parent.ink
                        }
                    }
                    Item {  // close
                        visible: cell.isClose
                        anchors.fill: parent
                        Rectangle { anchors.centerIn: parent; width: parent.width * 1.32; height: parent.parent.t; radius: height / 2; rotation: 45; color: parent.parent.ink }
                        Rectangle { anchors.centerIn: parent; width: parent.width * 1.32; height: parent.parent.t; radius: height / 2; rotation: -45; color: parent.parent.ink }
                    }
                }

                HoverHandler { id: hover }
                TapHandler { id: press; onTapped: Caption.command(cell.modelData) }
            }
        }
    }
}
