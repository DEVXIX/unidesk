import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// All of xD in one widget, rather than one widget per thing it does.
//
// It is a stack one level deep: a menu of what xD has, and whichever of those
// you opened, with "<" to come back. Everything shares the one session, so
// signing in once is the whole setup.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    implicitWidth: opt("width", 340)
    implicitHeight: opt("height", 400)

    // "" is the menu; anything else is a section. A conversation is a section
    // with somebody's name after it, which is the only two-level path here.
    property string section: ""
    property string openWith: ""

    readonly property var sections: [
        { key: "messages", label: "Messages", icon: Icons.comment },
        { key: "alerts", label: "Notifications", icon: Icons.notifications },
        { key: "tweets", label: "Timeline", icon: Icons.format_list_bulleted },
        { key: "quests", label: "Quests", icon: Icons.task_alt },
        { key: "wordle", label: "Wordle", icon: Icons.emoji_events },
        { key: "rooms", label: "Rooms", icon: Icons.group }
    ]

    function labelOf(key) {
        for (var i = 0; i < sections.length; i++) if (sections[i].key === key) return sections[i].label;
        return "xD";
    }
    function nameOf(row) { return row.username || row.handle || row.name || row.user || ""; }
    function textOf(row) {
        return row.content || row.text || row.body || row.message || row.title || "";
    }

    function go(key) {
        section = key;
        openWith = "";
        if (key === "messages") XD.refresh();
        else if (key === "wordle") XD.loadWordle();
        else if (key !== "alerts") XD.loadSection(key);
    }
    function back() {
        if (openWith !== "") openWith = "";
        else section = "";
    }

    // ---- header ---------------------------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 14 }
        height: 26

        MIcon {
            id: lead
            anchors.verticalCenter: parent.verticalCenter
            icon: (root.section === "" && root.openWith === "") ? Icons.apps : Icons.chevron_right
            rotation: (root.section === "" && root.openWith === "") ? 0 : 180
            size: 18
            color: Theme.c.primary
            MouseArea {
                anchors.fill: parent; anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                enabled: root.section !== "" || root.openWith !== ""
                onClicked: root.back()
            }
        }
        UText {
            anchors { left: lead.right; leftMargin: 8; verticalCenter: parent.verticalCenter }
            text: root.openWith !== "" ? "@" + root.openWith
                : root.section === "" ? "xD" : root.labelOf(root.section)
            size: 15; weight: Font.Medium
        }
        Rectangle {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            visible: XD.signedIn && XD.badge > 0 && root.section === ""
            height: 20; radius: 10
            width: Math.max(20, badge.implicitWidth + 12)
            color: Theme.c.error
            UText { id: badge; anchors.centerIn: parent; text: XD.badge; size: 11; weight: Font.Bold; color: Theme.c.onError }
        }
    }

    Item {
        id: body
        anchors { top: head.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 14; rightMargin: 14; bottomMargin: 14; topMargin: 10 }

        // ---- signed out --------------------------------------------------------
        Column {
            anchors.fill: parent
            spacing: 8
            visible: !XD.signedIn

            UText {
                width: parent.width
                text: XD.error !== "" ? XD.error : "Sign in to xD."
                size: 12; wrapMode: Text.WordWrap
                color: XD.error !== "" ? Theme.c.error : Theme.c.onSurfaceVariant
            }
            Field { id: userField; width: parent.width; placeholder: "username" }
            Field {
                id: passField; width: parent.width; placeholder: "password"; secret: true
                onAccepted: XD.signIn(userField.text, passField.text)
            }
            Rectangle {
                width: parent.width; height: 34; radius: 17
                color: XD.busy ? Theme.c.surfaceContainerHighest : Theme.c.primary
                UText {
                    anchors.centerIn: parent
                    text: XD.busy ? "Signing in…" : "Sign in"
                    size: 13; weight: Font.Medium
                    color: XD.busy ? Theme.c.onSurfaceVariant : Theme.c.onPrimary
                }
                MouseArea {
                    anchors.fill: parent; enabled: !XD.busy
                    cursorShape: Qt.PointingHandCursor
                    onClicked: XD.signIn(userField.text, passField.text)
                }
            }
        }

        // ---- the menu ----------------------------------------------------------
        Flow {
            anchors.fill: parent
            visible: XD.signedIn && root.section === ""
            spacing: 8

            Repeater {
                model: root.sections
                delegate: Rectangle {
                    required property var modelData
                    width: (body.width - 8) / 2
                    height: 62
                    radius: 14
                    color: tile.containsMouse ? Theme.c.surfaceBright : Theme.c.surfaceContainerHighest
                    Column {
                        anchors.centerIn: parent
                        spacing: 4
                        MIcon {
                            anchors.horizontalCenter: parent.horizontalCenter
                            icon: modelData.icon; size: 20; color: Theme.c.primary
                        }
                        UText {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.label; size: 12; weight: Font.Medium
                        }
                    }
                    Rectangle {
                        visible: modelData.key === "messages" && XD.unread > 0
                        anchors { right: parent.right; top: parent.top; margins: 6 }
                        width: 18; height: 18; radius: 9
                        color: Theme.c.primary
                        UText { anchors.centerIn: parent; text: XD.unread; size: 10; weight: Font.Bold; color: Theme.c.onPrimary }
                    }
                    MouseArea {
                        id: tile
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.go(modelData.key)
                    }
                }
            }
        }

        // ---- messages: the people -----------------------------------------------
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "messages" && root.openWith === ""
            clip: true; spacing: 4
            model: XD.conversations
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 50
                Rectangle { anchors.fill: parent; radius: 12; color: Theme.c.onSurface; opacity: pick.containsMouse ? 0.07 : 0 }
                Column {
                    anchors { left: parent.left; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    spacing: 2
                    UText { width: parent.width; text: root.nameOf(modelData) || "someone"; size: 13; weight: Font.Medium; elide: Text.ElideRight }
                    UText { width: parent.width; text: root.textOf(modelData); size: 11.5; color: Theme.c.onSurfaceVariant; elide: Text.ElideRight }
                }
                MouseArea {
                    id: pick
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { root.openWith = root.nameOf(modelData); XD.openThread(root.openWith); }
                }
            }
        }

        // ---- messages: one conversation ------------------------------------------
        ListView {
            id: thread
            anchors { top: parent.top; left: parent.left; right: parent.right; bottom: composer.top; bottomMargin: 8 }
            visible: XD.signedIn && root.openWith !== ""
            clip: true; spacing: 4
            model: XD.thread
            onCountChanged: positionViewAtEnd()
            delegate: Item {
                required property var modelData
                readonly property bool mine: root.nameOf(modelData) === XD.me
                width: ListView.view.width
                height: bubble.height
                Rectangle {
                    id: bubble
                    x: parent.mine ? parent.width - width : 0
                    width: Math.min(parent.width * 0.85, line.implicitWidth + 22)
                    height: line.implicitHeight + 14
                    radius: 14
                    color: parent.mine ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                    UText {
                        id: line
                        anchors.centerIn: parent
                        width: bubble.width - 22
                        text: root.textOf(modelData)
                        size: 12.5; wrapMode: Text.WordWrap
                        color: bubble.parent.mine ? Theme.c.onPrimaryContainer : Theme.c.onSurface
                    }
                }
            }
        }
        Field {
            id: composer
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            visible: XD.signedIn && root.openWith !== ""
            placeholder: "Message @" + root.openWith
            onAccepted: { if (text.trim() !== "") { XD.send(root.openWith, text); text = ""; } }
        }

        // ---- everything else: one list, one shape ---------------------------------
        // Notifications, the timeline, quests and rooms are all "a line of text
        // with somebody's name under it", so they are drawn once rather than
        // four times. Opening one hands it to the website.
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && ["alerts", "tweets", "quests", "rooms"].indexOf(root.section) >= 0
            clip: true; spacing: 2
            model: root.section === "alerts" ? XD.notifications : XD.section
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 46
                Rectangle { anchors.fill: parent; radius: 10; color: Theme.c.onSurface; opacity: hit.containsMouse ? 0.07 : 0 }
                Column {
                    anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                    spacing: 1
                    UText { width: parent.width; text: root.textOf(modelData) || "—"; size: 12.5; elide: Text.ElideRight }
                    UText {
                        width: parent.width
                        visible: root.nameOf(modelData) !== ""
                        text: "@" + root.nameOf(modelData)
                        size: 11; color: Theme.c.onSurfaceVariant; elide: Text.ElideRight
                    }
                }
                MouseArea {
                    id: hit
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: XD.open(root.section === "alerts" ? "notifications" : root.section)
                }
            }
        }

        // ---- wordle ---------------------------------------------------------------
        Column {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "wordle"
            spacing: 10

            UText {
                width: parent.width
                text: {
                    var w = XD.wordle && XD.wordle.stats ? XD.wordle.stats : ({});
                    var streak = w.current_streak !== undefined ? w.current_streak : (w.streak || 0);
                    return "Streak " + streak + " · played " + (w.played || w.games_played || 0);
                }
                size: 12; color: Theme.c.onSurfaceVariant
            }
            Field {
                id: guessField
                width: parent.width
                placeholder: "your guess"
                onAccepted: { if (text.trim() !== "") { XD.guess(text); text = ""; } }
            }
            UText {
                width: parent.width
                text: "Type a word and press Enter. It is scored on xD."
                size: 11; color: Theme.c.onSurfaceVariant; wrapMode: Text.WordWrap
            }
        }

        // nothing to show
        UText {
            anchors.centerIn: parent
            visible: XD.signedIn && root.section !== "" && root.section !== "wordle" && root.openWith === ""
                     && (root.section === "alerts" ? XD.notifications.length === 0 : XD.section.length === 0)
            text: XD.busy ? "Loading…" : "Nothing here"
            size: 12; color: Theme.c.onSurfaceVariant
        }
    }

    // A text box in the desk's own clothes. focusInput is what actually makes it
    // typeable: a desk window does not take the keyboard until it is told to,
    // which is why widgets never steal focus from whatever you are doing.
    component Field: Rectangle {
        id: field
        property alias text: input.text
        property string placeholder: ""
        property bool secret: false
        signal accepted()
        height: 34
        radius: 17
        color: Theme.c.surfaceContainerHighest
        border.width: input.activeFocus ? 1 : 0
        border.color: Theme.c.primary
        TextInput {
            id: input
            anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 13
            font.family: Theme.font
            color: Theme.c.onSurface
            selectionColor: Theme.c.primary
            selectedTextColor: Theme.c.onPrimary
            echoMode: field.secret ? TextInput.Password : TextInput.Normal
            selectByMouse: true
            onActiveFocusChanged: Desk.focusInput(Window.window, activeFocus)
            onAccepted: field.accepted()
        }
        UText {
            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
            visible: input.text === "" && !input.activeFocus
            text: field.placeholder
            size: 12.5
            color: Theme.c.onSurfaceVariant
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.IBeamCursor
            onClicked: input.forceActiveFocus()
        }
    }
}
