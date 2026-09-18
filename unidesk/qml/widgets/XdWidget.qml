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
        { key: "games", label: "Games", icon: Icons.sports_esports },
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
        else if (key === "tweets" || key === "rooms") XD.loadSection(key);
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
                Avatar { id: face; url: modelData.avatar; size: 34; anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter } }
                Column {
                    anchors { left: face.right; leftMargin: 10; right: dot.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                    spacing: 2
                    UText { width: parent.width; text: modelData.name || modelData.handle; size: 13; weight: Font.Medium; elide: Text.ElideRight }
                    UText { width: parent.width; text: modelData.last; size: 11.5; color: Theme.c.onSurfaceVariant; elide: Text.ElideRight }
                }
                Rectangle {
                    id: dot
                    anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    visible: (modelData.unread || 0) > 0
                    width: 18; height: 18; radius: 9
                    color: Theme.c.primary
                    UText { anchors.centerIn: parent; text: modelData.unread; size: 10; weight: Font.Bold; color: Theme.c.onPrimary }
                }
                MouseArea {
                    id: pick
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { root.openWith = modelData.handle; XD.openThread(modelData.handle); }
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
            visible: XD.signedIn && ["alerts", "rooms"].indexOf(root.section) >= 0
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
        // The real board: /wordle/today answers the guesses so far, how long the
        // word is and whether it is done, so the grid is drawn from that rather
        // than kept here - reopening the widget shows the game where you left it.
        Column {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "wordle"
            spacing: 10

            readonly property var game: (XD.wordle && XD.wordle.today) ? XD.wordle.today : ({})
            readonly property int letters: game.word_length || 5
            readonly property var rows: game.guesses || []
            readonly property string status: String(game.status || "")

            Column {
                id: board
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 4
                Repeater {
                    model: 6
                    delegate: Row {
                        required property int index
                        readonly property var guess: index < parent.parent.rows.length ? parent.parent.rows[index] : null
                        spacing: 4
                        Repeater {
                            model: parent.parent.parent.letters
                            delegate: Rectangle {
                                required property int index
                                readonly property var g: parent.guess
                                // a guess is either "word" or {word, result[]}
                                readonly property string word: g ? String(g.word || g.guess || g) : ""
                                readonly property var marks: g && g.result ? g.result : null
                                readonly property string mark: marks && index < marks.length ? String(marks[index]) : ""
                                width: 30; height: 30; radius: 7
                                color: !word ? Theme.c.surfaceContainerHighest
                                     : mark === "correct" || mark === "2" ? Theme.c.primary
                                     : mark === "present" || mark === "1" ? Theme.c.tertiaryContainer
                                     : Theme.c.surfaceBright
                                UText {
                                    anchors.centerIn: parent
                                    text: word.length > index ? word.charAt(index).toUpperCase() : ""
                                    size: 14; weight: Font.Bold
                                    color: (mark === "correct" || mark === "2") ? Theme.c.onPrimary : Theme.c.onSurface
                                }
                            }
                        }
                    }
                }
            }

            Field {
                id: guessField
                width: parent.width
                visible: parent.status !== "won" && parent.status !== "lost"
                placeholder: parent.letters + " letters, then Enter"
                onAccepted: { if (text.trim() !== "") { XD.guess(text); text = ""; } }
            }
            UText {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: parent.status === "won" ? "Got it." : parent.status === "lost" ? "Out of guesses." : ""
                visible: text !== ""
                size: 12.5; weight: Font.Medium; color: Theme.c.primary
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

        // ---- the timeline ---------------------------------------------------------
        // A tweet is a person and a thing they posted, so it is drawn as one:
        // their picture and name, the words, and the image if there is one.
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "tweets"
            clip: true; spacing: 8
            model: XD.section
            delegate: Item {
                required property var modelData
                readonly property var who: modelData.author || ({})
                readonly property var media: (modelData.media_urls && modelData.media_urls.length > 0)
                    ? modelData.media_urls[0] : null
                width: ListView.view.width
                height: col.implicitHeight + 14

                Rectangle { anchors.fill: parent; radius: 12; color: Theme.c.surfaceContainerHighest; opacity: 0.55 }
                Avatar {
                    id: pic
                    url: who.profile_picture || ""
                    size: 28
                    anchors { left: parent.left; leftMargin: 8; top: parent.top; topMargin: 8 }
                }
                Column {
                    id: col
                    anchors { left: pic.right; leftMargin: 8; right: parent.right; rightMargin: 8; top: parent.top; topMargin: 7 }
                    spacing: 4
                    Row {
                        spacing: 5
                        UText { text: who.display_name || who.username || "someone"; size: 12.5; weight: Font.Medium }
                        UText { text: who.username ? "@" + who.username : ""; size: 11.5; color: Theme.c.onSurfaceVariant }
                    }
                    UText {
                        width: col.width
                        visible: (modelData.content || "") !== ""
                        text: modelData.content
                        size: 12; wrapMode: Text.WordWrap
                        maximumLineCount: 4; elide: Text.ElideRight
                    }
                    Image {
                        visible: media !== null && media.type === "image"
                        source: media ? media.url : ""
                        width: col.width
                        fillMode: Image.PreserveAspectCrop
                        // capped, so one tall picture cannot push the rest of the
                        // timeline off the bottom of the widget
                        height: visible ? Math.min(150, width * 0.62) : 0
                        asynchronous: true
                        clip: true
                    }
                    Row {
                        spacing: 12
                        UText { text: "♥ " + (modelData.likes_count || 0); size: 11; color: Theme.c.onSurfaceVariant }
                        UText { text: "↺ " + (modelData.retweets_count || 0); size: 11; color: Theme.c.onSurfaceVariant }
                        UText { text: "✎ " + (modelData.replies_count || 0); size: 11; color: Theme.c.onSurfaceVariant }
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: XD.open("tweet/" + modelData.id)
                }
            }
        }

        // ---- games ----------------------------------------------------------------
        // The widget has no browser in it, so a game opens on the website. The
        // daily ones come first because they are the ones with a streak to keep.
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "games"
            clip: true; spacing: 3
            model: XD.games
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 38
                Rectangle { anchors.fill: parent; radius: 10; color: Theme.c.onSurface; opacity: play.containsMouse ? 0.08 : 0 }
                Row {
                    anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
                    spacing: 8
                    MIcon {
                        icon: modelData.daily ? Icons.emoji_events : Icons.sports_esports
                        size: 15
                        color: modelData.daily ? Theme.c.primary : Theme.c.onSurfaceVariant
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    UText { text: modelData.name; size: 12.5; anchors.verticalCenter: parent.verticalCenter }
                }
                MouseArea {
                    id: play
                    anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: XD.open("games/" + modelData.slug)
                }
            }
        }

    // Somebody's picture, or the first letter of their name when they have none.
    component Avatar: Rectangle {
        property string url: ""
        property int size: 32
        property string fallback: ""
        width: size; height: size; radius: size / 2
        color: Theme.c.surfaceBright
        clip: true
        UText {
            anchors.centerIn: parent
            visible: pic.status !== Image.Ready
            text: fallback ? fallback.charAt(0).toUpperCase() : "?"
            size: parent.size * 0.4
            color: Theme.c.onSurfaceVariant
        }
        Image {
            id: pic
            anchors.fill: parent
            source: parent.url
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            visible: status === Image.Ready
            layer.enabled: true
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
