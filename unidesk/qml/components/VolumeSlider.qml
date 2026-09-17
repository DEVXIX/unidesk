import QtQuick
import QtQuick.Controls.Basic

// A thick Material 3 slider: filled part, gap, rest of the track, pill handle.
// `moved(value)` fires while dragging so volume follows the finger.
Slider {
    id: slider
    property color activeColor: Theme.c.primary
    property color trackColor: Theme.c.secondaryContainer
    signal moved2(real value)

    from: 0
    to: 1
    height: 30
    focusPolicy: Qt.NoFocus
    onMoved: moved2(value)

    background: Item {
        x: slider.leftPadding
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: slider.availableWidth
        height: 16
        Rectangle {
            width: Math.max(0, slider.visualPosition * parent.width - 4)
            height: parent.height
            radius: 6
            color: slider.activeColor
        }
        Rectangle {
            x: slider.visualPosition * parent.width + 4
            width: Math.max(0, parent.width - x)
            height: parent.height
            radius: 6
            color: slider.trackColor
        }
    }
    handle: Rectangle {
        x: slider.leftPadding + slider.visualPosition * slider.availableWidth - width / 2
        y: slider.topPadding + slider.availableHeight / 2 - height / 2
        width: 4
        height: slider.pressed ? 30 : 26
        radius: 2
        color: slider.activeColor
        Behavior on height { NumberAnimation { duration: 120 } }
    }
}
