import QtQuick

// A small button that says what it does. Filled for the one you probably
// mean, outlined for the others.
Rectangle {
    id: pill
    property string label: ""
    property bool filled: false
    property bool small: false
    signal pressed()

    width: text.implicitWidth + (small ? 16 : 22)
    height: small ? 22 : 26
    radius: height / 2
    color: filled ? Theme.c.primary : "transparent"
    border.width: filled ? 0 : 1.5
    border.color: Theme.c.outline

    UText {
        id: text
        anchors.centerIn: parent
        text: pill.label
        size: pill.small ? 10.5 : 11.5
        weight: Font.Medium
        color: pill.filled ? Theme.c.onPrimary : Theme.c.onSurface
    }
    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: pill.filled ? Theme.c.onPrimary : Theme.c.onSurface
        opacity: mouse.pressed ? 0.18 : mouse.containsMouse ? 0.08 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: pill.pressed()
    }
}
