import QtQuick
import QtQuick.Controls.Basic
import "../components"
import "../Icons.js" as Icons

// A sticky note or a to-do list (option mode: note | todo), saved as you type.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property bool todo: opt("mode", "note") === "todo"
    property var todos: []
    tone: opt("tone", "tertiary")

    function reload() { if (widgetId) todos = Notes.todos(widgetId); }
    onWidgetIdChanged: { reload(); if (widgetId) noteArea.text = Notes.text(widgetId); }
    Connections { target: Notes; function onChanged(id) { if (id === root.widgetId) root.reload(); } }

    implicitWidth: opt("width", 300)
    implicitHeight: todo ? Math.max(160, todoColumn.implicitHeight + 28) : opt("height", 220)

    UText {
        x: 16; y: 12
        text: root.opt("title", root.todo ? "To do" : "Note")
        size: 16; weight: Font.Medium
        color: root.onColor
    }
    MIcon {
        anchors { right: parent.right; rightMargin: 14; top: parent.top; topMargin: 12 }
        icon: root.todo ? Icons.format_list_bulleted : Icons.edit_note
        size: 20; color: root.onColor; opacity: 0.7
    }

    // ---- note --------------------------------------------------------------------
    ScrollView {
        visible: !root.todo
        anchors { fill: parent; topMargin: 42; leftMargin: 10; rightMargin: 10; bottomMargin: 10 }
        TextArea {
            id: noteArea
            wrapMode: TextEdit.Wrap
            font.family: Theme.font
            font.pixelSize: root.opt("font_size", 15)
            color: root.onColor
            placeholderText: "Write something…"
            placeholderTextColor: Qt.alpha(root.onColor, 0.5)
            selectionColor: Theme.c.primary
            selectedTextColor: Theme.c.onPrimary
            background: null
            onActiveFocusChanged: Desk.focusInput(Window.window, activeFocus)
            onTextChanged: if (root.widgetId) Notes.setText(root.widgetId, text)
        }
    }

    // ---- to-do ---------------------------------------------------------------------
    Column {
        id: todoColumn
        visible: root.todo
        x: 12; y: 44
        width: parent.width - 24
        spacing: 2

        Repeater {
            model: root.todos
            delegate: Item {
                required property var modelData
                required property int index
                width: todoColumn.width; height: 36
                Rectangle { anchors.fill: parent; radius: 12; color: root.onColor; opacity: todoHover.hovered ? 0.07 : 0 }
                MIcon {
                    id: box
                    x: 6; anchors.verticalCenter: parent.verticalCenter
                    icon: modelData.done ? Icons.check_box : Icons.check_box_outline_blank
                    size: 22; fill: modelData.done ? 1 : 0
                    color: root.onColor
                }
                UText {
                    anchors { left: box.right; leftMargin: 10; right: del.left; rightMargin: 4; verticalCenter: parent.verticalCenter }
                    text: modelData.text
                    size: 14
                    color: root.onColor
                    opacity: modelData.done ? 0.5 : 1
                    font.strikeout: modelData.done
                }
                MouseArea { anchors.fill: parent; anchors.rightMargin: 34; cursorShape: Qt.PointingHandCursor; onClicked: Notes.toggleTodo(root.widgetId, index) }
                IconButton {
                    id: del
                    visible: todoHover.hovered
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    icon: Icons.close; size: 28; iconSize: 15; iconColor: root.onColor
                    onClicked: Notes.removeTodo(root.widgetId, index)
                }
                HoverHandler { id: todoHover }
            }
        }

        Rectangle {
            width: parent.width; height: 38; radius: 19
            color: Qt.alpha(root.onColor, 0.08)
            MIcon { id: plus; x: 12; anchors.verticalCenter: parent.verticalCenter; icon: Icons.add; size: 18; color: root.onColor }
            TextInput {
                id: newTodo
                anchors { left: plus.right; leftMargin: 8; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                font.family: Theme.font
                font.pixelSize: 14
                color: root.onColor
                clip: true
                onActiveFocusChanged: Desk.focusInput(Window.window, activeFocus)
                onAccepted: { Notes.addTodo(root.widgetId, text); text = ""; }
                UText { visible: !newTodo.text && !newTodo.activeFocus; text: "Add a task"; size: 14; color: root.onColor; opacity: 0.55; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
}
