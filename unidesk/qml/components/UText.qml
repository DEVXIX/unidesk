import QtQuick

// Text in the theme font (Google Sans Flex, with its roundness axis).
Text {
    property int weight: Font.Normal
    property real size: 14

    font.family: Theme.font
    font.pixelSize: size
    font.weight: weight
    font.variableAxes: ({ "ROND": Theme.roundness, "wght": weight })
    color: Theme.c.onSurface
    elide: Text.ElideRight
    Behavior on color { ColorAnimation { duration: 500 * Theme.animationSpeed } }
}
