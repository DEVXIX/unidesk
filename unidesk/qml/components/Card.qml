import QtQuick
import QtQuick.Effects

// The rounded surface most widgets sit on, with a soft shadow.
// tone: surface | high | highest | primary | secondary | tertiary
Item {
    id: root
    property string tone: "surface"
    property real radius: Theme.radius
    property alias color: bg.color
    default property alias content: inner.data

    readonly property color onColor: ({
        surface: Theme.c.onSurface, high: Theme.c.onSurface, highest: Theme.c.onSurface,
        primary: Theme.c.onPrimaryContainer, secondary: Theme.c.onSecondaryContainer, tertiary: Theme.c.onTertiaryContainer
    })[tone] || Theme.c.onSurface

    RectangularShadow {
        anchors.fill: bg
        visible: Theme.shadows
        radius: bg.radius
        blur: 18
        spread: -2
        offset.y: 4
        color: Qt.rgba(0, 0, 0, 0.28)
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: root.radius
        color: ({
            surface: Theme.c.surfaceContainerHigh, high: Theme.c.surfaceContainerHighest, highest: Theme.c.surfaceBright,
            primary: Theme.c.primaryContainer, secondary: Theme.c.secondaryContainer, tertiary: Theme.c.tertiaryContainer
        })[root.tone] || Theme.c.surfaceContainer
        opacity: Theme.cardOpacity
        Behavior on color { ColorAnimation { duration: 600 * Theme.animationSpeed } }
    }

    Item {
        id: inner
        anchors.fill: parent
    }
}
