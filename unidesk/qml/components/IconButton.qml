import QtQuick

// A round (or shaped) icon button with a hover state layer.
Item {
    id: root
    property string icon: ""
    property real size: 36
    property real iconSize: size * 0.55
    property string shape: ""           // "" = circle, or an MShape name
    property color color: "transparent"
    property color iconColor: Theme.c.onSurface
    property real fill: 0
    property bool outlined: false
    signal clicked()

    width: size
    height: size

    Rectangle {
        anchors.fill: parent
        visible: root.shape === ""
        radius: width / 2
        color: root.color
        border.width: root.outlined ? 1.5 : 0
        border.color: Theme.c.outline
        Behavior on color { ColorAnimation { duration: 400 } }
    }
    MShape {
        anchors.fill: parent
        visible: root.shape !== ""
        shape: root.shape || "circle"
        color: root.color
        rotation: mouse.pressed ? 20 : 0
        Behavior on rotation { NumberAnimation { duration: 300; easing.type: Easing.OutBack } }
    }
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: root.iconColor
        opacity: mouse.pressed ? 0.16 : mouse.containsMouse ? 0.08 : 0
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }
    MIcon {
        anchors.centerIn: parent
        icon: root.icon
        size: root.iconSize
        fill: root.fill
        color: root.iconColor
        scale: mouse.pressed ? 0.88 : 1
        Behavior on scale { NumberAnimation { duration: 150 } }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
