import QtQuick
import QtQuick.Window

// One line of a form: a label above what you type.
//
// A desk window will not take the keyboard unless it is told to, so focusing
// the box is what asks for it, and losing focus gives it straight back.
Rectangle {
    id: field
    property string label: ""
    property string placeholder: ""
    property bool secret: false
    property alias text: input.text
    signal accepted()

    width: parent ? parent.width : 200
    height: 34
    radius: 8
    color: Theme.c.surfaceContainerHigh
    border.width: input.activeFocus ? 1.5 : 0
    border.color: Theme.c.primary

    UText {
        anchors { left: parent.left; leftMargin: 8; top: parent.top; topMargin: 3 }
        text: field.label
        size: 9
        color: input.activeFocus ? Theme.c.primary : Theme.c.onSurfaceVariant
    }
    TextInput {
        id: input
        anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8; bottom: parent.bottom; bottomMargin: 5 }
        font.family: Theme.font
        font.pixelSize: 12
        color: Theme.c.onSurface
        echoMode: field.secret ? TextInput.Password : TextInput.Normal
        selectByMouse: true
        clip: true
        onActiveFocusChanged: Desk.focusInput(Window.window, activeFocus)
        onAccepted: field.accepted()
        Component.onDestruction: if (activeFocus && Window.window) Desk.focusInput(Window.window, false);

        UText {
            visible: !input.text && !input.activeFocus
            text: field.placeholder
            size: 12
            color: Theme.c.onSurfaceVariant
            opacity: 0.5
        }
    }
}
