import QtQuick
import QtQuick.Controls.Basic
import "../Icons.js" as Icons

// One editable option: a switch, a row of choice chips, a slider or a text box.
// Emits changed(value) when the user commits (slider release, Enter, click).
Column {
    id: row
    property var field: ({})
    property var value
    signal changed(var value)

    readonly property var current: value === undefined || value === null ? field.def : value
    width: parent ? parent.width : 260
    spacing: 6

    Item {
        width: parent.width
        height: Math.max(label.implicitHeight, field.kind === "bool" ? 28 : 0)
        UText {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            text: row.field.label
            size: 13.5
            weight: Font.Medium
            color: Theme.c.onSurface
        }
        UText {
            visible: row.field.kind === "slider"
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            text: slider.pressed ? Math.round(slider.value * 100) / 100 : row.current
            size: 13
            color: Theme.c.onSurfaceVariant
            font.features: { "tnum": 1 }
        }

        // switch
        Rectangle {
            visible: row.field.kind === "bool"
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            width: 50; height: 28; radius: 14
            color: row.current ? Theme.c.primary : Theme.c.surfaceContainerHighest
            border.width: row.current ? 0 : 2
            border.color: Theme.c.outline
            Behavior on color { ColorAnimation { duration: 180 } }
            Rectangle {
                width: row.current ? 20 : 14; height: width; radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                x: row.current ? parent.width - width - 4 : 7
                color: row.current ? Theme.c.onPrimary : Theme.c.outline
                Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                Behavior on width { NumberAnimation { duration: 180 } }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: row.changed(!row.current) }
        }
    }

    // choice chips
    Flow {
        visible: row.field.kind === "choice"
        width: parent.width
        spacing: 6
        Repeater {
            model: row.field.kind === "choice" ? row.field.options : []
            Rectangle {
                required property string modelData
                readonly property bool on: String(row.current) === modelData
                height: 32; radius: 10
                width: chipText.implicitWidth + (on ? 38 : 24)
                color: on ? Theme.c.secondaryContainer : "transparent"
                border.width: on ? 0 : 1
                border.color: Theme.c.outlineVariant
                Behavior on width { NumberAnimation { duration: 150 } }
                Row {
                    anchors.centerIn: parent
                    spacing: 4
                    MIcon { visible: parent.parent.on; icon: Icons.check; size: 16; color: Theme.c.onSecondaryContainer; anchors.verticalCenter: parent.verticalCenter }
                    UText { id: chipText; text: modelData; size: 13; color: parent.parent.on ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: row.changed(modelData) }
            }
        }
    }

    // slider
    Slider {
        id: slider
        visible: row.field.kind === "slider"
        width: parent.width
        height: 28
        from: row.field.min || 0
        to: row.field.max || 1
        stepSize: row.field.step || 0
        snapMode: Slider.SnapAlways
        value: Number(row.current)
        onPressedChanged: if (!pressed && value !== Number(row.current)) row.changed(value)

        background: Item {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: slider.availableWidth
            height: 14
            Rectangle {
                width: Math.max(0, slider.visualPosition * parent.width - 5)
                height: parent.height; radius: 5
                color: Theme.c.primary
            }
            Rectangle {
                x: slider.visualPosition * parent.width + 5
                width: Math.max(0, parent.width - x)
                height: parent.height; radius: 5
                color: Theme.c.secondaryContainer
            }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * slider.availableWidth - width / 2
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: 4; height: slider.pressed ? 30 : 26; radius: 2
            color: Theme.c.primary
        }
    }

    // text
    TextField {
        id: textBox
        visible: row.field.kind === "text" || row.field.kind === "secret"
        width: parent.width
        height: 40
        text: row.field.kind === "text" || row.field.kind === "secret" ? String(row.current || "") : ""
        echoMode: row.field.kind === "secret" ? TextInput.Password : TextInput.Normal
        font.family: Theme.font
        font.pixelSize: 14
        color: Theme.c.onSurface
        selectionColor: Theme.c.primary
        selectedTextColor: Theme.c.onPrimary
        leftPadding: 12
        placeholderText: "Enter to apply"
        placeholderTextColor: Theme.c.onSurfaceVariant
        background: Rectangle {
            radius: 12
            color: Theme.c.surfaceContainerHighest
            border.width: textBox.activeFocus ? 2 : 1
            border.color: textBox.activeFocus ? Theme.c.primary : Theme.c.outlineVariant
        }
        onAccepted: row.changed(text)
        onActiveFocusChanged: if (!activeFocus && text !== String(row.current || "")) row.changed(text)
    }
}
