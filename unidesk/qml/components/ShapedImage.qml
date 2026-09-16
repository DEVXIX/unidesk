import QtQuick
import QtQuick.Effects

// An image cropped to fill, clipped to a rounded rectangle (radius) or an
// expressive shape (shape: "star", "cookie", ...).
Item {
    id: root
    property url source
    property string shape: ""
    property real radius: 16
    property color placeholder: Theme.c.surfaceContainerHighest
    readonly property bool ready: img.status === Image.Ready

    Image {
        id: img
        anchors.fill: parent
        source: root.source
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        sourceSize: Qt.size(Math.ceil(root.width * 2), Math.ceil(root.height * 2))
        visible: false
    }

    Item {
        id: mask
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle {
            anchors.fill: parent
            visible: root.shape === ""
            radius: root.radius
            color: "black"
        }
        MShape {
            anchors.fill: parent
            visible: root.shape !== ""
            shape: root.shape || "circle"
            color: "black"
        }
    }

    // Placeholder while there is no image.
    Rectangle {
        anchors.fill: parent
        visible: !root.ready && root.shape === ""
        radius: root.radius
        color: root.placeholder
    }
    MShape {
        anchors.fill: parent
        visible: !root.ready && root.shape !== ""
        shape: root.shape || "circle"
        color: root.placeholder
    }

    MultiEffect {
        anchors.fill: parent
        source: img
        visible: root.ready
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
        opacity: root.ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 300 } }
    }
}
