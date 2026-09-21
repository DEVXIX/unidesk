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
    property bool multiline: false
    property string text: ""
    // Set by whichever box is inside, so the outline knows to light up.
    property bool focused: false
    signal accepted()

    width: parent ? parent.width : 200
    height: 34
    radius: 8
    color: Theme.c.surfaceContainerHigh
    border.width: field.focused ? 1.5 : 0
    border.color: Theme.c.primary

    UText {
        anchors { left: parent.left; leftMargin: 8; top: parent.top; topMargin: 3 }
        text: field.label
        size: 9
        color: field.focused ? Theme.c.primary : Theme.c.onSurfaceVariant
    }
    // One line or several. A TextEdit for the second kind, because headers and
    // a JSON body are both things you paste rather than type.
    Loader {
        id: box
        anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8;
                  top: parent.top; topMargin: 14; bottom: parent.bottom; bottomMargin: 5 }
        sourceComponent: field.multiline ? manyLines : oneLine
    }

    Component {
        id: oneLine
        TextInput {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            font.family: Theme.font
            font.pixelSize: 12
            color: Theme.c.onSurface
            echoMode: field.secret ? TextInput.Password : TextInput.Normal
            selectByMouse: true
            clip: true
            text: field.text
            onTextChanged: field.text = text
            onActiveFocusChanged: { field.focused = activeFocus; Desk.focusInput(Window.window, activeFocus); }
            onAccepted: field.accepted()
            Component.onDestruction: if (activeFocus && Window.window) Desk.focusInput(Window.window, false);
        }
    }
    Component {
        id: manyLines
        Flickable {
            anchors.fill: parent
            contentHeight: edit.height
            clip: true
            TextEdit {
                id: edit
                width: parent.width
                wrapMode: TextEdit.Wrap
                font.family: "Consolas"
                font.pixelSize: 12
                color: Theme.c.onSurface
                selectByMouse: true
                text: field.text
                onTextChanged: field.text = text
                onActiveFocusChanged: { field.focused = activeFocus; Desk.focusInput(Window.window, activeFocus); }
                Component.onDestruction: if (activeFocus && Window.window) Desk.focusInput(Window.window, false);
            }
        }
    }

    UText {
        anchors { left: parent.left; leftMargin: 8; top: parent.top; topMargin: field.multiline ? 15 : 14 }
        visible: field.text === ""
        text: field.placeholder
        size: 12
        color: Theme.c.onSurfaceVariant
        opacity: 0.5
    }
}
