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
    // The picture being looked at, "" for none. It covers the whole widget
    // rather than opening a window: a widget that spawns windows is a program.
    property string viewing: ""
    // The tweet being read, 0 for none. Opening one used to hand it to a
    // browser, which is a strange thing for a desktop widget to do.
    property int openTweetId: 0
    // Watching what somebody sends, full size.
    property bool watchFullScreen: false

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
        XD.closeThread();
        XD.viewing(key);
        if (key === "messages") XD.refresh();
        else if (key === "wordle") XD.loadWordle();
        else if (key === "tweets" || key === "rooms") XD.loadSection(key);
    }
    function back() {
        // Leaving something also stops the poll keeping it up to date.
        if (openTweetId !== 0) { openTweetId = 0; XD.closeTweet(); }
        else if (openWith !== "") { openWith = ""; XD.closeThread(); }
        else { section = ""; XD.viewing(""); }
    }
    function readTweet(id) { openTweetId = id; XD.openTweet(id); }
    function whenOf(row) {
        var raw = row && (row.created_at || row.sort_time);
        if (!raw) return "";
        var mins = Math.max(0, Math.round((Date.now() - new Date(raw).getTime()) / 60000));
        if (mins < 1) return "now";
        if (mins < 60) return mins + "m";
        if (mins < 1440) return Math.round(mins / 60) + "h";
        return Math.round(mins / 1440) + "d";
    }

    // ---- header ---------------------------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 14 }
        height: 26

        MIcon {
            id: lead
            anchors.verticalCenter: parent.verticalCenter
            readonly property bool atRoot: root.section === "" && root.openWith === "" && root.openTweetId === 0
            icon: atRoot ? Icons.apps : Icons.chevron_right
            rotation: atRoot ? 0 : 180
            size: 18
            color: Theme.c.primary
            MouseArea {
                anchors.fill: parent; anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                enabled: !lead.atRoot
                onClicked: root.back()
            }
        }
        UText {
            anchors { left: lead.right; leftMargin: 8; verticalCenter: parent.verticalCenter }
            text: Calls.inCall ? "Call"
                : root.openTweetId !== 0 ? "Tweet"
                : root.openWith !== "" ? "@" + root.openWith
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

        // ---- a call, while there is one --------------------------------------
        // It takes the widget over rather than sitting in a corner of it: while
        // a call is up, everything you might want is about the call. The ring
        // itself is elsewhere (CallCard.qml) - by the time you are looking at
        // this, it has been answered.
        Flickable {
            anchors.fill: parent
            visible: Calls.inCall
            contentHeight: callPage.implicitHeight
            clip: true
            interactive: contentHeight > height
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: callPage
                width: parent.width
                spacing: 9

                // ---- what they are sending ------------------------------------
                Rectangle {
                    width: parent.width
                    height: visible ? Math.round(width * 0.56) : 0
                    visible: Calls.videoKind !== ""
                    radius: 12
                    color: "#000000"
                    clip: true

                    Image {
                        id: remoteVideo
                        anchors.fill: parent
                        fillMode: Image.PreserveAspectFit
                        cache: false
                        asynchronous: false
                        // The tick is what makes Qt fetch it again: the same url
                        // would be served from the cache forever.
                        source: Calls.videoKind !== "" ? "image://xdcall/f" + Calls.videoTick : ""
                    }

                    UText {
                        anchors { left: parent.left; top: parent.top; margins: 7 }
                        text: Calls.videoKind === "screen" ? "their screen" : "their camera"
                        size: 10.5
                        color: "#ffffff"
                        opacity: 0.75
                    }

                    // Full screen, for when a widget is too small to read what
                    // somebody is showing you - which is most of the time.
                    Rectangle {
                        anchors { right: parent.right; top: parent.top; margins: 6 }
                        width: 26; height: 26; radius: 13
                        color: Qt.rgba(0, 0, 0, 0.55)
                        MIcon { anchors.centerIn: parent; icon: Icons.open_in_full; size: 13; color: "#ffffff" }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.watchFullScreen = true
                        }
                    }
                }

                Row {
                    spacing: 10
                    ShapedImage {
                        width: 46; height: 46
                        shape: "cookie"
                        source: Calls.call.avatar || ""
                        visible: (Calls.call.avatar || "") !== ""
                    }
                    MShape {
                        width: 46; height: 46
                        shape: "cookie"
                        color: Theme.c.surfaceContainerHighest
                        visible: (Calls.call.avatar || "") === ""
                    }
                    Column {
                        spacing: 1
                        UText { text: Calls.call.name || "someone"; size: 14.5; weight: Font.Medium }
                        UText {
                            text: Calls.call.handle ? "@" + Calls.call.handle : ""
                            size: 11.5; color: Theme.c.onSurfaceVariant
                        }
                        UText {
                            // The thing you look at to know it is still up.
                            text: Calls.connected ? Calls.duration : "Connecting..."
                            size: 12; color: Theme.c.primary
                        }
                    }
                }

                UText { text: "Volume"; size: 11.5; color: Theme.c.onSurfaceVariant }
                VolumeSlider {
                    width: parent.width
                    value: Calls.volume
                    onMoved2: (v) => Calls.setVolume(v)
                }

                UText { text: "Microphone"; size: 11.5; color: Theme.c.onSurfaceVariant }
                Column {
                    width: parent.width
                    spacing: 3
                    Repeater {
                        model: Calls.inputs
                        Rectangle {
                            required property var modelData
                            width: callPage.width
                            height: 28
                            radius: 14
                            color: modelData.id === Calls.inputId ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                            UText {
                                anchors { left: parent.left; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                                text: modelData.name
                                size: 11.5
                                elide: Text.ElideRight
                                color: modelData.id === Calls.inputId ? Theme.c.onPrimaryContainer : Theme.c.onSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Calls.setInput(modelData.id)
                            }
                        }
                    }
                }

                UText {
                    text: "Camera"
                    size: 11.5; color: Theme.c.onSurfaceVariant
                    visible: Calls.cameras.length > 0
                }
                Column {
                    width: parent.width
                    spacing: 3
                    visible: Calls.cameras.length > 0
                    Repeater {
                        model: Calls.cameras
                        Rectangle {
                            required property var modelData
                            width: callPage.width
                            height: 28
                            radius: 14
                            color: modelData.id === Calls.cameraId ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                            UText {
                                anchors { left: parent.left; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                                text: modelData.name
                                size: 11.5
                                elide: Text.ElideRight
                                color: modelData.id === Calls.cameraId ? Theme.c.onPrimaryContainer : Theme.c.onSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Calls.setCamera(modelData.id)
                            }
                        }
                    }
                }

                UText { text: "Speakers"; size: 11.5; color: Theme.c.onSurfaceVariant }
                Column {
                    width: parent.width
                    spacing: 3
                    Repeater {
                        model: Calls.outputs
                        Rectangle {
                            required property var modelData
                            width: callPage.width
                            height: 28
                            radius: 14
                            color: modelData.id === Calls.outputId ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                            UText {
                                anchors { left: parent.left; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                                text: modelData.name
                                size: 11.5
                                elide: Text.ElideRight
                                color: modelData.id === Calls.outputId ? Theme.c.onPrimaryContainer : Theme.c.onSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Calls.setOutput(modelData.id)
                            }
                        }
                    }
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 10
                    topPadding: 4

                    Rectangle {
                        width: 44; height: 44; radius: 22
                        color: Calls.muted ? Theme.c.surfaceContainerHighest : Theme.c.primaryContainer
                        MIcon {
                            anchors.centerIn: parent
                            icon: Calls.muted ? Icons.mic_off : Icons.mic
                            size: 19
                            color: Calls.muted ? Theme.c.onSurfaceVariant : Theme.c.onPrimaryContainer
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Calls.toggleMute() }
                    }

                    Rectangle {
                        width: 44; height: 44; radius: 22
                        color: Calls.cameraOn ? Theme.c.primaryContainer : Theme.c.surfaceContainerHighest
                        MIcon {
                            anchors.centerIn: parent
                            icon: Calls.cameraOn ? Icons.videocam : Icons.videocam_off
                            size: 19
                            color: Calls.cameraOn ? Theme.c.onPrimaryContainer : Theme.c.onSurfaceVariant
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Calls.toggleCamera() }
                    }

                    Rectangle {
                        width: 44; height: 44; radius: 22
                        color: "#d9463c"
                        MIcon { anchors.centerIn: parent; icon: Icons.call_end; size: 19; color: "#ffffff" }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Calls.hangUp() }
                    }
                }

                UText {
                    width: parent.width
                    visible: Calls.error !== ""
                    text: Calls.error
                    size: 11; color: Theme.c.error; wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        // ---- signed out --------------------------------------------------------
        Column {
            anchors.fill: parent
            spacing: 8
            visible: !XD.signedIn && !Calls.inCall

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
            visible: XD.signedIn && root.section === "" && !Calls.inCall
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
            visible: XD.signedIn && root.section === "messages" && root.openWith === "" && !Calls.inCall
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
            visible: XD.signedIn && root.openWith !== "" && !Calls.inCall
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
            visible: XD.signedIn && root.openWith !== "" && !Calls.inCall
            placeholder: "Message @" + root.openWith
            onAccepted: { if (text.trim() !== "") { XD.send(root.openWith, text); text = ""; } }
        }

        // ---- everything else: one list, one shape ---------------------------------
        // Notifications, the timeline, quests and rooms are all "a line of text
        // with somebody's name under it", so they are drawn once rather than
        // four times. Opening one hands it to the website.
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && ["alerts", "rooms"].indexOf(root.section) >= 0 && !Calls.inCall
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
            visible: XD.signedIn && root.section === "wordle" && !Calls.inCall
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

        // ---- the timeline ---------------------------------------------------------
        // A tweet is a person and a thing they posted, so it is drawn as one:
        // their picture and name, the words, and the image if there is one.
        ListView {
            anchors {
                top: parent.top; left: parent.left; right: parent.right
                bottom: tweetBox.top; bottomMargin: 8
            }
            visible: XD.signedIn && root.section === "tweets" && root.openTweetId === 0 && !Calls.inCall
            clip: true; spacing: 8
            id: timeline
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
                    // Small on the timeline and rounded like everything else;
                    // the full picture is a tap away rather than in your way.
                    ShapedImage {
                        visible: media !== null && media.type === "image"
                        source: media ? media.url : ""
                        width: col.width
                        height: visible ? Math.round(width * 0.42) : 0
                        radius: 12
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: (mouse) => { root.viewing = media.url; mouse.accepted = true; }
                        }
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
                    z: -1   // the picture and the heart get first refusal
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.readTweet(modelData.id)
                }
            }
        }

        // ---- writing one ----------------------------------------------------------
        // Text only, and one line of it: a widget is where you say something
        // short. Anything longer, or with a picture on it, belongs on the site.
        Item {
            id: tweetBox
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            visible: XD.signedIn && root.section === "tweets" && root.openTweetId === 0 && !Calls.inCall
            height: visible ? 34 : 0

            Field {
                id: tweetField
                anchors { left: parent.left; right: sendTweet.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                placeholder: "What's happening?"
                onAccepted: XD.post(text)
            }
            Rectangle {
                id: sendTweet
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: 34; height: 34; radius: 17
                readonly property bool ready: tweetField.text.trim() !== "" && !XD.busy
                color: ready ? Theme.c.primary : Theme.c.surfaceContainerHighest
                MIcon {
                    anchors.centerIn: parent
                    icon: Icons.arrow_upward
                    size: 16
                    color: sendTweet.ready ? Theme.c.onPrimary : Theme.c.onSurfaceVariant
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: sendTweet.ready
                    cursorShape: Qt.PointingHandCursor
                    onClicked: XD.post(tweetField.text)
                }
            }
            // Cleared only once it is really on the timeline, so a refusal does
            // not also lose what you wrote.
            Connections {
                target: XD
                function onPosted() { tweetField.text = ""; }
            }
        }

        // ---- one tweet, read here --------------------------------------------------
        // The whole thing rather than four lines of it: every picture, what
        // people said back, and a box to say something yourself. Opening a
        // browser for this was the widget admitting it could not do the job.
        Item {
            id: reader
            anchors.fill: parent
            visible: XD.signedIn && root.openTweetId !== 0 && !Calls.inCall

            ListView {
                anchors {
                    top: parent.top; left: parent.left; right: parent.right
                    bottom: replyBox.top; bottomMargin: 8
                }
                clip: true; spacing: 8
                model: XD.replies

                header: Column {
                    id: full
                    width: ListView.view.width
                    spacing: 7
                    bottomPadding: 6

                    readonly property var t: XD.tweet || ({})
                    readonly property var who: t.author || ({})

                    Row {
                        spacing: 8
                        Avatar { url: full.who.profile_picture || ""; size: 34 }
                        Column {
                            spacing: 1
                            UText {
                                text: full.who.display_name || full.who.username || "someone"
                                size: 13.5; weight: Font.Medium
                            }
                            UText {
                                text: (full.who.username ? "@" + full.who.username : "")
                                    + (root.whenOf(full.t) ? " · " + root.whenOf(full.t) : "")
                                size: 11.5; color: Theme.c.onSurfaceVariant
                            }
                        }
                    }
                    UText {
                        width: parent.width
                        visible: (full.t.content || "") !== ""
                        text: full.t.content || ""
                        size: 13; wrapMode: Text.WordWrap
                    }
                    // Every picture on it, not just the first.
                    Repeater {
                        model: full.t.media_urls || []
                        ShapedImage {
                            required property var modelData
                            visible: modelData && modelData.type === "image"
                            source: visible ? modelData.url : ""
                            width: reader.width
                            height: visible ? Math.round(width * 0.52) : 0
                            radius: 12
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.viewing = modelData.url
                            }
                        }
                    }
                    Row {
                        spacing: 14
                        // A Row cannot hold a fill-anchored child, so the heart
                        // and its count sit in an Item that the tap area can fill.
                        Item {
                            width: heart.implicitWidth; height: heart.implicitHeight
                            Row {
                                id: heart
                                spacing: 4
                                UText {
                                    text: "♥"; size: 13
                                    color: full.t.is_liked_by_me ? Theme.c.error : Theme.c.onSurfaceVariant
                                }
                                UText {
                                    text: full.t.likes_count || 0
                                    size: 12; color: Theme.c.onSurfaceVariant
                                }
                            }
                            MouseArea {
                                anchors.fill: parent; anchors.margins: -6
                                cursorShape: Qt.PointingHandCursor
                                onClicked: XD.like(root.openTweetId, !full.t.is_liked_by_me)
                            }
                        }
                        UText {
                            text: "↺ " + (full.t.retweets_count || 0)
                            size: 12; color: Theme.c.onSurfaceVariant
                        }
                        UText {
                            text: "✎ " + (full.t.replies_count || 0)
                            size: 12; color: Theme.c.onSurfaceVariant
                        }
                    }
                    Rectangle { width: parent.width; height: 1; color: Theme.c.outlineVariant; opacity: 0.5 }
                    UText {
                        visible: XD.replies.length === 0
                        text: XD.busy ? "Loading…" : "No replies yet"
                        size: 12; color: Theme.c.onSurfaceVariant
                    }
                }

                delegate: Item {
                    id: replyRow
                    required property var modelData
                    readonly property var who: modelData.author || ({})
                    width: ListView.view.width
                    height: rcol.implicitHeight + 12

                    Rectangle { anchors.fill: parent; radius: 10; color: Theme.c.surfaceContainerHighest; opacity: 0.45 }
                    Avatar {
                        id: rpic
                        url: replyRow.who.profile_picture || ""
                        size: 22
                        anchors { left: parent.left; leftMargin: 7; top: parent.top; topMargin: 7 }
                    }
                    Column {
                        id: rcol
                        anchors { left: rpic.right; leftMargin: 7; right: parent.right; rightMargin: 7; top: parent.top; topMargin: 6 }
                        spacing: 2
                        Row {
                            spacing: 5
                            UText {
                                text: replyRow.who.display_name || replyRow.who.username || "someone"
                                size: 12; weight: Font.Medium
                            }
                            UText {
                                text: replyRow.who.username ? "@" + replyRow.who.username : ""
                                size: 11; color: Theme.c.onSurfaceVariant
                            }
                        }
                        UText {
                            width: rcol.width
                            text: replyRow.modelData.content || ""
                            size: 12; wrapMode: Text.WordWrap
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.readTweet(modelData.id)
                    }
                }
            }

            Field {
                id: replyBox
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                placeholder: "Reply"
                onAccepted: XD.reply(root.openTweetId, text)
                Connections {
                    target: XD
                    function onPosted() { replyBox.text = ""; }
                }
            }
        }

        // ---- games ----------------------------------------------------------------
        // The widget has no browser in it, so a game opens on the website. The
        // daily ones come first because they are the ones with a streak to keep.
        ListView {
            anchors.fill: parent
            visible: XD.signedIn && root.section === "games" && !Calls.inCall
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

    }

    // ---- watching it properly ------------------------------------------------------
    Rectangle {
        anchors.fill: parent
        visible: root.watchFullScreen && Calls.videoKind !== ""
        radius: Theme.radius
        color: "#000000"
        z: 12

        Image {
            anchors { fill: parent; margins: 4 }
            fillMode: Image.PreserveAspectFit
            cache: false
            asynchronous: false
            source: parent.visible ? "image://xdcall/full" + Calls.videoTick : ""
        }
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 10 }
            width: 28; height: 28; radius: 14
            color: Qt.rgba(1, 1, 1, 0.16)
            MIcon { anchors.centerIn: parent; icon: Icons.close; size: 15; color: "#ffffff" }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.watchFullScreen = false
        }
    }

    // ---- looking at a picture ----------------------------------------------------
    Rectangle {
        anchors.fill: parent
        visible: root.viewing !== ""
        radius: Theme.radius
        color: Qt.rgba(0, 0, 0, 0.92)
        z: 10

        ShapedImage {
            anchors { fill: parent; margins: 10 }
            source: root.viewing
            radius: 12
        }
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 12 }
            width: 28; height: 28; radius: 14
            color: Theme.c.surfaceContainerHighest
            MIcon { anchors.centerIn: parent; icon: Icons.close; size: 15; color: Theme.c.onSurface }
        }
        // Anywhere closes it, which is what everybody tries first.
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.viewing = ""
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
