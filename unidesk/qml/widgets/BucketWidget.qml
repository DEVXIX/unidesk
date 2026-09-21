import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// Object storage on the desk: Amazon S3, MinIO, or anything else that speaks
// the same protocol.
//
// It browses rather than syncs. Buckets, then folders, then files - click a
// file and it lands in Downloads. Nothing is uploaded, moved or deleted from
// here: a widget you click by accident should not be able to lose anything.
//
// Keys are kept the same way the terminal keeps passwords - encrypted for
// this Windows account, and only after a connection has actually worked.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    implicitWidth: opt("width", 380)
    implicitHeight: opt("height", 420)

    readonly property string connectionName: String(opt("connection", ""))
    property string phase: "idle"
    property string message: ""
    property var entries: []
    property bool canSave: false
    property string suggested: ""
    property string sheet: ""

    function ident() { return widgetId !== "" ? widgetId : ""; }
    function refresh() {
        if (ident() === "") return;
        phase = Buckets.state(ident());
        message = Buckets.message(ident());
        entries = Buckets.entries(ident());
        canSave = Buckets.offersSave(ident());
        if (canSave) suggested = Buckets.suggestedName(ident());
        if (phase === "ready" && sheet === "connect") sheet = "";
    }
    function connectSaved(name, announce) {
        if (announce) Desk.setOption(root.widgetId, "connection", name);
        Buckets.openSaved(ident(), name);
        sheet = "";
    }
    function startIfReady() {
        if (ident() === "") return;
        refresh();
        if (connectionName !== "" && phase === "idle") connectSaved(connectionName, false);
    }
    Component.onCompleted: startIfReady()
    onWidgetIdChanged: startIfReady()

    Connections {
        target: Buckets
        function onStateChanged(who) { if (who === root.ident()) root.refresh(); }
        function onSavedChanged() { root.refresh(); }
    }

    function sizeOf(bytes) {
        if (!bytes) return "";
        var units = ["B", "KB", "MB", "GB", "TB"], n = bytes, i = 0;
        while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
        return (i === 0 ? n : n.toFixed(n < 10 ? 1 : 0)) + " " + units[i];
    }

    // ---- header ---------------------------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 12 }
        height: 26

        MIcon {
            id: lead
            anchors.verticalCenter: parent.verticalCenter
            icon: Icons.cloud
            size: 18
            color: root.phase === "ready" ? Theme.c.primary : Theme.c.onSurfaceVariant
            MouseArea {
                anchors.fill: parent
                anchors.margins: -6
                enabled: Buckets.canGoUp(root.ident())
                cursorShape: Qt.PointingHandCursor
                onClicked: Buckets.up(root.ident())
            }
        }
        UText {
            anchors { left: lead.right; leftMargin: 8; right: tools.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
            text: root.phase === "idle" ? (root.opt("label", "") || "Storage")
                                        : Buckets.where(root.ident())
            size: 14; weight: Font.Medium
            elide: Text.ElideLeft
        }
        Row {
            id: tools
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: 1
            IconButton {
                visible: Buckets.canGoUp(root.ident())
                icon: Icons.expand_less; size: 24; iconSize: 14
                iconColor: Theme.c.onSurfaceVariant
                onClicked: Buckets.up(root.ident())
            }
            IconButton {
                visible: root.phase === "ready" || root.phase === "failed"
                icon: Icons.refresh; size: 24; iconSize: 13
                iconColor: Theme.c.onSurfaceVariant
                onClicked: Buckets.refresh(root.ident())
            }
            IconButton {
                icon: Icons.expand_more; size: 24; iconSize: 13
                iconColor: Theme.c.onSurfaceVariant
                onClicked: root.sheet = root.sheet === "pick" ? "" : "pick"
            }
        }
    }

    // ---- what is in there -----------------------------------------------------
    Item {
        id: body
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
        anchors { top: head.bottom; topMargin: 6 }

        ListView {
            id: list
            anchors.fill: parent
            anchors.bottomMargin: saveBar.visible ? saveBar.height + 6 : 0
            clip: true
            spacing: 1
            visible: root.sheet === "" && root.phase !== "idle"
            model: root.entries

            delegate: Rectangle {
                required property var modelData
                width: list.width
                height: 32
                radius: 8
                color: hover.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"

                readonly property bool isFile: modelData.kind === "object"

                MIcon {
                    id: kindIcon
                    anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                    icon: modelData.kind === "bucket" ? Icons.hard_drive
                        : modelData.kind === "folder" ? Icons.folder : Icons.description
                    size: 15
                    color: parent.isFile ? Theme.c.onSurfaceVariant : Theme.c.primary
                }
                UText {
                    anchors { left: kindIcon.right; leftMargin: 8; right: size.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                    text: modelData.name
                    size: 12
                    elide: Text.ElideMiddle
                }
                UText {
                    id: size
                    anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    text: hover.containsMouse && parent.isFile ? "Download" : root.sizeOf(modelData.size)
                    size: 10
                    color: hover.containsMouse && parent.isFile ? Theme.c.primary : Theme.c.onSurfaceVariant
                }
                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (parent.isFile) Buckets.download(root.ident(), modelData.name);
                        else Buckets.enter(root.ident(), modelData.name);
                    }
                }
            }
        }

        // Busy, empty, or broken.
        Column {
            anchors.centerIn: parent
            width: parent.width - 24
            spacing: 6
            visible: root.sheet === "" && (root.phase === "connecting" || root.phase === "loading"
                     || root.phase === "failed" || (root.phase === "ready" && root.entries.length === 0))

            UText {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.phase === "connecting" ? "Connecting..."
                    : root.phase === "loading" ? "Loading..."
                    : root.phase === "failed" ? "That did not work" : "Nothing here"
                size: 13; weight: Font.Medium
            }
            UText {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                text: root.message
                size: 10.5; color: Theme.c.onSurfaceVariant
            }
            Pill {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.phase === "failed"
                label: "Change connection"
                onPressed: root.sheet = "pick"
            }
        }

        // Somewhere to choose from, when nothing is open yet.
        Loader {
            anchors.fill: parent
            active: root.sheet === "pick" || (root.sheet === "" && root.phase === "idle")
            sourceComponent: picker
        }
        Loader {
            anchors.fill: parent
            active: root.sheet === "connect"
            sourceComponent: form
        }

        // "Save these keys?", once they are known to work.
        // With somewhere to type what to call it: the endpoint it was reached
        // at is a fine default and a poor name.
        Rectangle {
            id: saveBar
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 40
            radius: 8
            color: Theme.c.primaryContainer
            visible: root.canSave && root.sheet === ""

            function keepIt() {
                var name = naming.text.trim() || root.suggested;
                if (name === "") return;
                Buckets.saveConnection(root.ident(), name);
                Desk.setOption(root.widgetId, "connection", name);
                naming.text = "";
            }

            Field {
                id: naming
                anchors { left: parent.left; leftMargin: 5; right: buttons.left; rightMargin: 5; verticalCenter: parent.verticalCenter }
                height: 32
                label: "Save this as"
                placeholder: root.suggested
                onAccepted: saveBar.keepIt()
            }
            Row {
                id: buttons
                anchors { right: parent.right; rightMargin: 5; verticalCenter: parent.verticalCenter }
                spacing: 4
                Pill { label: "Save"; filled: true; small: true; onPressed: saveBar.keepIt() }
                Pill { label: "No"; small: true; onPressed: Buckets.declineSave(root.ident()) }
            }
        }
    }

    // ---- the saved ones --------------------------------------------------------
    Component {
        id: picker
        Item {
            Column {
                anchors.fill: parent
                spacing: 5
                UText { text: "Connect to"; size: 11; color: Theme.c.onSurfaceVariant }
                ListView {
                    width: parent.width
                    height: Math.max(0, parent.height - 60)
                    clip: true
                    model: Buckets.saved
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 30
                        radius: 7
                        color: pick.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"
                        Column {
                            anchors { left: parent.left; leftMargin: 8; right: drop.left; verticalCenter: parent.verticalCenter }
                            UText { text: modelData.name; size: 12; weight: Font.Medium; width: parent.width; elide: Text.ElideRight }
                            UText {
                                text: modelData.endpoint || "Amazon S3"
                                size: 9.5; color: Theme.c.onSurfaceVariant
                                width: parent.width; elide: Text.ElideMiddle
                            }
                        }
                        IconButton {
                            id: drop
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                            visible: pick.containsMouse
                            icon: Icons.delete_; size: 20; iconSize: 11
                            iconColor: Theme.c.onSurfaceVariant
                            onClicked: Buckets.forget(modelData.name)
                        }
                        MouseArea {
                            id: pick
                            anchors.fill: parent
                            anchors.rightMargin: 22
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.connectSaved(modelData.name, true)
                        }
                    }
                }
                Pill { label: "New connection"; filled: true; onPressed: root.sheet = "connect" }
            }
        }
    }

    // ---- a new one -------------------------------------------------------------
    Component {
        id: form
        Flickable {
            contentHeight: fields.height
            clip: true
            Column {
                id: fields
                width: parent.width
                spacing: 5

                Field {
                    id: fEndpoint
                    label: "Endpoint (blank for Amazon S3)"
                    placeholder: "http://192.168.1.10:9000"
                }
                Row {
                    spacing: 5
                    Field { id: fKey; label: "Access key"; width: (fields.width - 5) * 0.5 }
                    Field { id: fRegion; label: "Region"; text: "us-east-1"; width: (fields.width - 5) * 0.5 }
                }
                Field { id: fSecret; label: "Secret key"; secret: true }
                Field { id: fBucket; label: "Bucket (optional)"; placeholder: "all of them" }

                Row {
                    spacing: 5
                    Pill {
                        label: "Connect"; filled: true
                        onPressed: {
                            Buckets.open(root.ident(), {
                                endpoint: fEndpoint.text, region: fRegion.text,
                                access_key: fKey.text, secret_key: fSecret.text,
                                bucket: fBucket.text
                            });
                            root.sheet = "";
                        }
                    }
                    Pill { label: "Cancel"; onPressed: root.sheet = "pick" }
                }
            }
        }
    }
}
