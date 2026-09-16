import QtQuick

// A Material Symbols Rounded glyph. `icon` takes a name from Icons.js.
Text {
    property string icon: ""
    property real size: 20
    property real fill: 0

    text: icon
    font.family: Theme.iconFont
    font.pixelSize: size
    font.variableAxes: ({ "FILL": fill, "opsz": Math.max(20, Math.min(48, size)), "wght": 450 })
    color: Theme.c.onSurface
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    Behavior on color { ColorAnimation { duration: 500 * Theme.animationSpeed } }
}
