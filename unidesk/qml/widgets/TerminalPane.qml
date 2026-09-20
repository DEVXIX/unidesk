import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// One terminal: the screen, or whatever is standing between you and it.
//
// A pane is one of up to four in an ssh widget, and each keeps its own
// session, so `paneId` - not the widget's id - is what the provider is asked
// about. Everything it shows is pulled in when the provider says something
// changed rather than bound to a property, because a screen is a list of a
// thousand little things and rebuilding it on every binding check would cost
// more than the terminal itself.
Item {
    id: pane
    property string paneId: ""
    property string connectionName: ""
    property bool typing: false
    property bool compact: false
    signal chose(string name)
    signal cleared()

    property string phase: "idle"
    property string message: ""
    property string screenText: ""
    property bool canSave: false
    // "" is the terminal itself; anything else is a form over the top of it.
    property string sheet: ""

    readonly property color ink: Theme.c.onSurface
    readonly property int cellWidth: Math.max(1, Math.round(metrics.advanceWidth("M")))
    readonly property int cellHeight: Math.max(1, Math.round(metrics.height))

    FontMetrics { id: metrics; font.family: "Consolas"; font.pixelSize: pane.compact ? 11 : 12.5 }

    function refreshState() {
        phase = Terminals.state(paneId);
        message = Terminals.message(paneId);
        canSave = Terminals.offersSave(paneId);
        if (phase === "connected" && sheet === "connect") sheet = "";
    }
    function refreshScreen() { screenText = Terminals.html(paneId); }
    function fit() {
        if (cellWidth < 2 || cellHeight < 2) return;
        Terminals.resize(paneId, Math.floor(screenArea.width / cellWidth),
                                 Math.floor(screenArea.height / cellHeight));
    }
    // `announce` tells the widget to write this down. Restoring what was
    // already written must not: every pane announcing itself on startup is a
    // burst of config writes, each one reloading the desk underneath them.
    function connectSaved(name, announce) {
        pane.connectionName = name;
        if (announce) pane.chose(name);
        Terminals.openSaved(paneId, name);
        sheet = "";
    }
    function disconnect() {
        Terminals.close(paneId);
        pane.connectionName = "";
        pane.cleared();
        screenText = "";
        refreshState();
    }

    // The widget is told its own id just after it is built, not before, so a
    // pane created inside it starts life as ":0" and becomes "ssh-2:0" a
    // moment later. Starting a session on the first of those leaves it filed
    // under a name nothing will ever ask about again.
    // Worked out where it is used rather than kept in a property: a change
    // handler runs before the bindings that depend on the same value have
    // caught up, so a `ready` property read from onPaneIdChanged was still
    // answering about the id before last.
    function ready() { return paneId !== "" && paneId.charAt(0) !== ":"; }
    function startIfReady() {
        if (!ready()) return;
        refreshState();
        refreshScreen();
        if (connectionName !== "" && phase === "idle") connectSaved(connectionName, false);
    }
    Component.onCompleted: startIfReady()
    onPaneIdChanged: startIfReady()
    onWidthChanged: fit()
    onHeightChanged: fit()
    // The first pane to be told it can type, takes the keys.
    onTypingChanged: if (typing && phase === "connected" && !keys.activeFocus) keys.forceActiveFocus();

    Connections {
        target: Terminals
        function onStateChanged(ident) { if (ident === pane.paneId) pane.refreshState(); }
        function onScreenChanged(ident) { if (ident === pane.paneId) pane.refreshScreen(); }
    }

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.c.surfaceContainerHighest
        clip: true

        // ---- the screen ---------------------------------------------------
        Item {
            id: screenArea
            anchors { fill: parent; margins: 6; topMargin: bar.height + 4 }

            // One text item for the whole screen. A row each was tidier and
            // cost a rebuild of every row on every repaint.
            Text {
                width: parent.width
                textFormat: Text.RichText
                font.family: "Consolas"
                font.pixelSize: metrics.font.pixelSize
                lineHeight: 1.0
                color: pane.ink
                text: pane.screenText
            }
            // Typing goes here. The desk window only accepts the keyboard
            // while the widget's Type button is on, which is what keeps the
            // widgets out of the way of everything else.
            Item {
                id: keys
                anchors.fill: parent
                Keys.onPressed: (event) => {
                    Terminals.sendKey(pane.paneId, event.key, event.modifiers, event.text);
                    event.accepted = true;
                }
            }
            // Clicking the screen while the widget is in typing mode is what
            // puts the keys into THIS pane rather than one of its neighbours.
            MouseArea {
                anchors.fill: parent
                enabled: pane.typing && pane.phase === "connected"
                onClicked: keys.forceActiveFocus()
            }
        }

        // ---- what is in the way -------------------------------------------
        Rectangle {
            anchors.fill: parent
            color: Theme.c.surfaceContainerHighest
            visible: pane.sheet !== "" || pane.phase !== "connected"
            opacity: 0.97

            // Nothing chosen yet, or asked to choose again.
            Loader {
                anchors { fill: parent; margins: 8; topMargin: bar.height + 4 }
                active: parent.visible && (pane.sheet === "pick"
                    || (pane.sheet === "" && pane.phase === "idle"))
                sourceComponent: picker
            }
            Loader {
                anchors { fill: parent; margins: 8; topMargin: bar.height + 4 }
                active: parent.visible && pane.sheet === "connect"
                sourceComponent: form
            }

            // Busy, refused, or asking about a key.
            Column {
                anchors.centerIn: parent
                width: parent.width - 28
                spacing: 8
                visible: pane.sheet === "" && pane.phase !== "idle" && pane.phase !== "connected"

                UText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: pane.phase === "connecting" ? "Connecting..."
                        : pane.phase === "unknown-host" ? "This machine is new"
                        : pane.phase === "failed" ? "Could not connect"
                        : "Disconnected"
                    size: 13; weight: Font.Medium
                }
                UText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WrapAnywhere
                    maximumLineCount: 3
                    text: pane.message
                    size: 10.5; color: Theme.c.onSurfaceVariant
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 6
                    visible: pane.phase !== "connecting"

                    // Accepting a fingerprint is a decision, so it is a button
                    // you press, not something that happened while you waited.
                    Pill {
                        visible: pane.phase === "unknown-host"
                        label: "Trust and connect"
                        filled: true
                        onPressed: {
                            Terminals.acceptHost(pane.paneId);
                            if (pane.connectionName !== "") Terminals.openSaved(pane.paneId, pane.connectionName);
                        }
                    }
                    Pill {
                        label: pane.phase === "unknown-host" ? "No" : "Try again"
                        onPressed: {
                            if (pane.phase === "unknown-host") pane.disconnect();
                            else if (pane.connectionName !== "") Terminals.openSaved(pane.paneId, pane.connectionName);
                            else pane.sheet = "pick";
                        }
                    }
                    Pill {
                        label: "Change"
                        visible: pane.phase !== "unknown-host"
                        onPressed: pane.sheet = "pick"
                    }
                }
            }
        }

        // ---- the pane's own little bar -------------------------------------
        Item {
            id: bar
            anchors { top: parent.top; left: parent.left; right: parent.right; margins: 6 }
            height: 18

            MIcon {
                id: dot
                anchors.verticalCenter: parent.verticalCenter
                icon: Icons.terminal
                size: 12
                color: pane.phase === "connected" ? Theme.c.primary : Theme.c.onSurfaceVariant
            }
            UText {
                anchors { left: dot.right; leftMargin: 5; right: paneTools.left; rightMargin: 4; verticalCenter: parent.verticalCenter }
                text: pane.connectionName || Terminals.title(pane.paneId) || "No connection"
                size: 10.5; weight: Font.Medium
                color: Theme.c.onSurfaceVariant
            }
            Row {
                id: paneTools
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 1
                IconButton {
                    icon: Icons.expand_more; size: 18; iconSize: 11
                    iconColor: Theme.c.onSurfaceVariant
                    onClicked: pane.sheet = pane.sheet === "pick" ? "" : "pick"
                }
                IconButton {
                    visible: pane.phase === "connected"
                    icon: Icons.close; size: 18; iconSize: 11
                    iconColor: Theme.c.onSurfaceVariant
                    onClicked: pane.disconnect()
                }
            }
        }

        // ---- "save this login?", once it is known to work ------------------
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 6 }
            height: 30
            radius: 8
            color: Theme.c.primaryContainer
            visible: pane.phase === "connected" && pane.canSave

            UText {
                anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                text: "Save this login?"
                size: 11; weight: Font.Medium
                color: Theme.c.onPrimaryContainer
            }
            Row {
                anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                spacing: 4
                Pill {
                    label: "Save"; filled: true; small: true
                    onPressed: {
                        var name = Terminals.suggestedName(pane.paneId);
                        Terminals.saveConnection(pane.paneId, name);
                        pane.connectionName = name;
                        pane.chose(name);
                    }
                }
                Pill {
                    label: "Not now"; small: true
                    onPressed: Terminals.declineSave(pane.paneId)
                }
            }
        }
    }

    // ---- choosing a saved connection ---------------------------------------
    Component {
        id: picker
        Item {
            Column {
                anchors.fill: parent
                spacing: 4
                UText { text: "Connect to"; size: 11; color: Theme.c.onSurfaceVariant }
                ListView {
                    width: parent.width
                    height: Math.max(0, parent.height - 58)
                    clip: true
                    model: Terminals.saved
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 26
                        radius: 7
                        color: hover.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"
                        UText {
                            anchors { left: parent.left; leftMargin: 8; right: forget.left; verticalCenter: parent.verticalCenter }
                            text: modelData.name + "  " + (modelData.user || "") + "@" + (modelData.host || "")
                            size: 11
                        }
                        IconButton {
                            id: forget
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                            visible: hover.containsMouse
                            icon: Icons.delete_; size: 20; iconSize: 11
                            iconColor: Theme.c.onSurfaceVariant
                            onClicked: Terminals.forget(modelData.name)
                        }
                        MouseArea {
                            id: hover
                            anchors.fill: parent
                            anchors.rightMargin: 22
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: pane.connectSaved(modelData.name, true)
                        }
                    }
                }
                Pill { label: "New connection"; filled: true; onPressed: pane.sheet = "connect" }
            }
        }
    }

    // ---- a new one ---------------------------------------------------------
    Component {
        id: form
        Flickable {
            contentHeight: fields.height
            clip: true
            Column {
                id: fields
                width: parent.width
                spacing: 5

                Field { id: fHost; label: "Host"; placeholder: "example.com" }
                Row {
                    spacing: 5
                    Field { id: fUser; label: "User"; width: (fields.width - 5) * 0.62 }
                    Field { id: fPort; label: "Port"; text: "22"; width: (fields.width - 5) * 0.38 }
                }
                Field { id: fPassword; label: "Password"; secret: true }
                Field { id: fKey; label: "Key file (optional)"; placeholder: "C:\\Users\\you\\.ssh\\id_ed25519" }

                Row {
                    spacing: 5
                    Pill {
                        label: "Connect"; filled: true
                        onPressed: {
                            Terminals.open(pane.paneId, {
                                host: fHost.text, port: Number(fPort.text) || 22,
                                user: fUser.text, password: fPassword.text,
                                key_path: fKey.text, name: fHost.text
                            });
                            pane.connectionName = "";
                            pane.sheet = "";
                        }
                    }
                    Pill { label: "Cancel"; onPressed: pane.sheet = "pick" }
                }
            }
        }
    }
}
