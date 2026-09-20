import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// One pane: a machine you type at, or a bucket you look through.
//
// A pane is one of up to four in the same widget, and each keeps its own
// session, so `paneId` - not the widget's id - is what the providers are
// asked about. Which of the two it is comes from which saved connection you
// picked, so switching a pane from a terminal to storage is a matter of
// choosing a different name off the same list.
//
// Everything it shows is pulled in when a provider says something changed
// rather than bound to a property: a terminal screen is a thousand little
// things and rebuilding it on every binding check would cost more than the
// terminal itself.
Item {
    id: pane
    property string paneId: ""
    property string connectionName: ""
    property string kind: "ssh"          // "ssh" or "s3"
    property bool typing: false
    property bool compact: false
    signal chose(string kind, string name)
    signal cleared()

    property string phase: "idle"
    property string message: ""
    property string screenText: ""
    property bool canSave: false
    // "" is the session itself; anything else is a form over the top of it.
    property string sheet: ""

    readonly property bool storage: kind === "s3"
    readonly property bool live: storage ? (phase === "ready" || phase === "loading")
                                         : phase === "connected"

    readonly property color ink: Theme.c.onSurface
    readonly property int cellWidth: Math.max(1, Math.round(metrics.advanceWidth("M")))
    readonly property int cellHeight: Math.max(1, Math.round(metrics.height))

    FontMetrics { id: metrics; font.family: "Consolas"; font.pixelSize: pane.compact ? 11 : 12.5 }

    function refreshState() {
        if (storage) {
            phase = Buckets.state(paneId);
            message = Buckets.message(paneId);
            canSave = Buckets.offersSave(paneId);
        } else {
            phase = Terminals.state(paneId);
            message = Terminals.message(paneId);
            canSave = Terminals.offersSave(paneId);
        }
        if (live && sheet === "connect") sheet = "";
    }
    function refreshScreen() { if (!storage) screenText = Terminals.html(paneId); }
    function fit() {
        if (storage || cellWidth < 2 || cellHeight < 2) return;
        Terminals.resize(paneId, Math.floor(screenArea.width / cellWidth),
                                 Math.floor(screenArea.height / cellHeight));
    }

    // `announce` tells the widget to write this down. Restoring what was
    // already written must not: every pane announcing itself on startup is a
    // burst of config writes, each one reloading the desk underneath them.
    function connectSaved(which, name, announce) {
        pane.kind = which;
        pane.connectionName = name;
        if (announce) pane.chose(which, name);
        if (which === "s3") Buckets.openSaved(paneId, name);
        else Terminals.openSaved(paneId, name);
        sheet = "";
    }
    function disconnect() {
        if (storage) Buckets.close(paneId);
        else Terminals.close(paneId);
        pane.connectionName = "";
        pane.cleared();
        screenText = "";
        refreshState();
    }

    // Worked out where it is used rather than kept in a property: a change
    // handler runs before the bindings that depend on the same value have
    // caught up, so a `ready` property read from onPaneIdChanged was still
    // answering about the id before last.
    function ready() { return paneId !== "" && paneId.charAt(0) !== ":"; }
    function startIfReady() {
        if (!ready()) return;
        refreshState();
        refreshScreen();
        if (connectionName !== "" && phase === "idle") connectSaved(kind, connectionName, false);
    }
    Component.onCompleted: startIfReady()
    onPaneIdChanged: startIfReady()

    // A pane that is taken away - the widget closed, or the layout changed
    // from four panes to one - leaves a connection and the thread reading it
    // behind unless it says so. Nothing would ever look at that session
    // again, and it would keep the machine on the other end busy for the rest
    // of the session.
    Component.onDestruction: {
        if (paneId === "") return;
        if (storage) Buckets.close(paneId);
        else Terminals.close(paneId);
    }

    onWidthChanged: fit()
    onHeightChanged: fit()
    // The first pane to be told it can type, takes the keys.
    onTypingChanged: if (typing && live && !storage && !keys.activeFocus) keys.forceActiveFocus();

    Connections {
        target: Terminals
        function onStateChanged(ident) { if (ident === pane.paneId && !pane.storage) pane.refreshState(); }
        function onScreenChanged(ident) { if (ident === pane.paneId && !pane.storage) pane.refreshScreen(); }
    }
    Connections {
        target: Buckets
        function onStateChanged(ident) { if (ident === pane.paneId && pane.storage) pane.refreshState(); }
    }

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Theme.c.surfaceContainerHighest
        clip: true

        // ---- whichever of the two this pane is ----------------------------
        Item {
            id: screenArea
            anchors { fill: parent; margins: 6; topMargin: bar.height + 4 }

            // One text item for the whole terminal screen. A row each was
            // tidier and cost a rebuild of every row on every repaint.
            Text {
                visible: !pane.storage
                width: parent.width
                textFormat: Text.RichText
                font.family: "Consolas"
                font.pixelSize: metrics.font.pixelSize
                lineHeight: 1.0
                color: pane.ink
                text: pane.screenText
            }

            Loader {
                anchors.fill: parent
                active: pane.storage
                sourceComponent: BucketView {
                    ident: pane.paneId
                    compact: pane.compact
                }
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
                enabled: pane.typing && pane.live && !pane.storage
                onClicked: keys.forceActiveFocus()
            }
        }

        // ---- what is in the way -------------------------------------------
        Rectangle {
            anchors.fill: parent
            color: Theme.c.surfaceContainerHighest
            visible: pane.sheet !== "" || !pane.live
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
                visible: pane.sheet === "" && pane.phase !== "idle" && !pane.live

                UText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: pane.phase === "connecting" ? "Connecting..."
                        : pane.phase === "unknown-host" ? "This machine is new"
                        : pane.phase === "changed-host" ? "This machine's key has changed"
                        : pane.phase === "failed" ? "Could not connect"
                        : "Disconnected"
                    size: 13; weight: Font.Medium
                    color: pane.phase === "changed-host" ? Theme.c.error : Theme.c.onSurface
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
                        visible: pane.phase !== "changed-host"
                        onPressed: {
                            if (pane.phase === "unknown-host") pane.disconnect();
                            else if (pane.connectionName !== "") pane.connectSaved(pane.kind, pane.connectionName, false);
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
                icon: pane.storage ? Icons.cloud : Icons.terminal
                size: 12
                color: pane.live ? Theme.c.primary : Theme.c.onSurfaceVariant
            }
            UText {
                anchors { left: dot.right; leftMargin: 5; right: paneTools.left; rightMargin: 4; verticalCenter: parent.verticalCenter }
                text: pane.storage && pane.live ? Buckets.where(pane.paneId)
                    : pane.connectionName || Terminals.title(pane.paneId) || "No connection"
                size: 10.5; weight: Font.Medium
                color: Theme.c.onSurfaceVariant
                elide: Text.ElideLeft
            }
            Row {
                id: paneTools
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 1
                IconButton {
                    visible: pane.storage && pane.live && Buckets.canGoUp(pane.paneId)
                    icon: Icons.expand_less; size: 18; iconSize: 11
                    iconColor: Theme.c.onSurfaceVariant
                    onClicked: Buckets.up(pane.paneId)
                }
                IconButton {
                    icon: Icons.expand_more; size: 18; iconSize: 11
                    iconColor: Theme.c.onSurfaceVariant
                    onClicked: pane.sheet = pane.sheet === "pick" ? "" : "pick"
                }
                IconButton {
                    visible: pane.live
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
            visible: pane.live && pane.canSave && pane.sheet === ""

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
                        var name = pane.storage ? Buckets.suggestedName(pane.paneId)
                                                : Terminals.suggestedName(pane.paneId);
                        if (pane.storage) Buckets.saveConnection(pane.paneId, name);
                        else Terminals.saveConnection(pane.paneId, name);
                        pane.connectionName = name;
                        pane.chose(pane.kind, name);
                    }
                }
                Pill {
                    label: "Not now"; small: true
                    onPressed: pane.storage ? Buckets.declineSave(pane.paneId)
                                            : Terminals.declineSave(pane.paneId)
                }
            }
        }
    }

    // ---- choosing a saved connection ---------------------------------------
    //
    // Machines and buckets in one list, because "what should this pane show"
    // is one question. Which kind it is comes along with the name.
    readonly property var everything: {
        var out = [];
        var machines = Terminals.saved;
        for (var i = 0; i < machines.length; i++)
            out.push({ kind: "ssh", name: machines[i].name,
                       where: (machines[i].user || "") + "@" + (machines[i].host || "") });
        var buckets = Buckets.saved;
        for (var j = 0; j < buckets.length; j++)
            out.push({ kind: "s3", name: buckets[j].name,
                       where: buckets[j].endpoint || "Amazon S3" });
        return out;
    }

    Component {
        id: picker
        Item {
            Column {
                anchors.fill: parent
                spacing: 4
                UText { text: "Connect to"; size: 11; color: Theme.c.onSurfaceVariant }
                ListView {
                    width: parent.width
                    height: Math.max(0, parent.height - 62)
                    clip: true
                    model: pane.everything
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 28
                        radius: 7
                        color: hover.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"
                        MIcon {
                            id: what
                            anchors { left: parent.left; leftMargin: 7; verticalCenter: parent.verticalCenter }
                            icon: modelData.kind === "s3" ? Icons.cloud : Icons.terminal
                            size: 13
                            color: Theme.c.primary
                        }
                        UText {
                            anchors { left: what.right; leftMargin: 7; right: forget.left; verticalCenter: parent.verticalCenter }
                            text: modelData.name + "  " + modelData.where
                            size: 11
                            elide: Text.ElideRight
                        }
                        IconButton {
                            id: forget
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                            visible: hover.containsMouse
                            icon: Icons.delete_; size: 20; iconSize: 11
                            iconColor: Theme.c.onSurfaceVariant
                            onClicked: modelData.kind === "s3" ? Buckets.forget(modelData.name)
                                                               : Terminals.forget(modelData.name)
                        }
                        MouseArea {
                            id: hover
                            anchors.fill: parent
                            anchors.rightMargin: 22
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: pane.connectSaved(modelData.kind, modelData.name, true)
                        }
                    }
                }
                Row {
                    spacing: 5
                    Pill { label: "New machine"; filled: true; onPressed: { pane.kind = "ssh"; pane.sheet = "connect"; } }
                    Pill { label: "New bucket"; onPressed: { pane.kind = "s3"; pane.sheet = "connect"; } }
                }
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

                // An ssh login...
                Field { id: fHost; visible: !pane.storage; label: "Host"; placeholder: "example.com" }
                Row {
                    spacing: 5
                    visible: !pane.storage
                    Field { id: fUser; label: "User"; width: (fields.width - 5) * 0.62 }
                    Field { id: fPort; label: "Port"; text: "22"; width: (fields.width - 5) * 0.38 }
                }
                Field { id: fPassword; visible: !pane.storage; label: "Password"; secret: true }
                Field { id: fKey; visible: !pane.storage; label: "Key file (optional)"; placeholder: "C:\\Users\\you\\.ssh\\id_ed25519" }

                // ...or a bucket's keys.
                Field { id: fEndpoint; visible: pane.storage; label: "Endpoint (blank for Amazon S3)"; placeholder: "http://192.168.1.10:9000" }
                Row {
                    spacing: 5
                    visible: pane.storage
                    Field { id: fAccess; label: "Access key"; width: (fields.width - 5) * 0.5 }
                    Field { id: fRegion; label: "Region"; text: "us-east-1"; width: (fields.width - 5) * 0.5 }
                }
                Field { id: fSecret; visible: pane.storage; label: "Secret key"; secret: true }
                Field { id: fBucket; visible: pane.storage; label: "Bucket (optional)"; placeholder: "all of them" }

                Row {
                    spacing: 5
                    Pill {
                        label: "Connect"; filled: true
                        onPressed: {
                            if (pane.storage) {
                                Buckets.open(pane.paneId, {
                                    endpoint: fEndpoint.text, region: fRegion.text,
                                    access_key: fAccess.text, secret_key: fSecret.text,
                                    bucket: fBucket.text
                                });
                            } else {
                                Terminals.open(pane.paneId, {
                                    host: fHost.text, port: Number(fPort.text) || 22,
                                    user: fUser.text, password: fPassword.text,
                                    key_path: fKey.text, name: fHost.text
                                });
                            }
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
