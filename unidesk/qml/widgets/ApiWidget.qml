import QtQuick
import QtQuick.Window
import "../components"
import "../Icons.js" as Icons

// An API client on the desk: what you are asking on the left, what came back
// on the right.
//
// Method, address, body, headers and authentication down one side; status,
// timing and the response down the other. Enough of an API client for the
// question you ask twenty times a day, without opening a program to ask it.
//
// It behaves like a window - drag the bar, drag the corner, X to close.
//
// Nothing it holds goes in config.yaml. A bearer token, a password and
// whatever is in the headers box all live in the vault, encrypted for this
// Windows account, because a config file is the thing people paste into an
// issue when something goes wrong.
Card {
    id: root
    property var options: ({})
    property string widgetId: ""
    property var frame: null
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    property real heldWidth: 0
    property real heldHeight: 0
    implicitWidth: heldWidth > 0 ? heldWidth : opt("width", 780)
    implicitHeight: heldHeight > 0 ? heldHeight : opt("height", 470)

    // The request being written. Loaded from the vault once the widget knows
    // which one it is.
    property string method: "GET"
    property string address: ""
    property string headerText: ""
    property string bodyText: ""
    property string bodyType: "json"
    property string authType: "none"
    property string authToken: ""
    property string authUser: ""
    property string authPassword: ""
    property string authKeyName: ""
    property string authKeyValue: ""

    property string asking: "body"        // body | headers | auth
    property string showing: "body"       // body | headers
    property bool menuOpen: false
    property bool busy: false
    property var answer: ({})
    readonly property bool sendsBody: method !== "GET" && method !== "HEAD"

    function request() {
        return {
            method: root.method, url: root.address,
            headers: root.headerText, body: root.bodyText, body_type: root.bodyType,
            auth: { type: root.authType, token: root.authToken,
                    user: root.authUser, password: root.authPassword,
                    key_name: root.authKeyName, key_value: root.authKeyValue }
        };
    }
    function keep() { if (widgetId !== "") Api.keepDraft(widgetId, root.request()); }
    function refresh() {
        if (widgetId === "") return;
        busy = Api.busy(widgetId);
        answer = Api.answer(widgetId);
    }
    function fill(saved) {
        if (!saved) return;
        method = saved.method || "GET";
        address = saved.url || "";
        headerText = saved.headers || "";
        bodyText = saved.body || "";
        bodyType = saved.body_type || "json";
        authType = saved.auth_type || "none";
        authToken = saved.token || "";
        authUser = saved.user || "";
        authPassword = saved.password || "";
        authKeyName = saved.key_name || "";
        authKeyValue = saved.key_value || "";
        // The boxes stop following these the moment anybody types in them,
        // so they are told directly.
        urlBox.text = address;
        headerBox.text = headerText;
        bodyBox.text = bodyText;
        tokenBox.text = authToken;
        userBox.text = authUser;
        passwordBox.text = authPassword;
        keyNameBox.text = authKeyName;
        keyValueBox.text = authKeyValue;
    }
    function send() {
        if (widgetId === "" || address.trim() === "") return;
        keep();
        showing = "body";
        Api.send(widgetId, root.request());
    }
    function start() {
        if (widgetId === "") return;
        fill(Api.draft(widgetId));
        refresh();
    }

    Component.onCompleted: start()
    onWidgetIdChanged: start()
    Connections {
        target: Api
        function onChanged(who) { if (who === root.widgetId) root.refresh(); }
    }
    // Written down a moment after the typing stops, not on every keystroke.
    Timer { id: settle; interval: 700; onTriggered: root.keep() }

    readonly property color statusColour: {
        var code = answer.status || 0;
        if (answer.ok === undefined) return Theme.c.onSurfaceVariant;
        if (!answer.ok || code >= 500) return Theme.c.error;
        if (code >= 400) return "#e3c07b";
        if (code >= 200 && code < 300) return "#5ad67d";
        return Theme.c.onSurfaceVariant;
    }

    // ---- the bar you drag it by -------------------------------------------------
    Item {
        id: head
        anchors { top: parent.top; left: parent.left; right: parent.right; margins: 12 }
        height: 24

        MouseArea {
            anchors { fill: parent; margins: -8 }
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.ArrowCursor
            property point grabbed
            property real fromX
            property real fromY
            onPressed: (e) => {
                if (e.button === Qt.RightButton) { root.menuOpen = true; return; }
                if (!root.frame) return;
                grabbed = mapToItem(root.frame.parent, e.x, e.y);
                fromX = root.frame.x;
                fromY = root.frame.y;
                root.frame.startMove();
            }
            onPositionChanged: (e) => {
                if (!pressed || !root.frame || !root.frame.dragging) return;
                var now = mapToItem(root.frame.parent, e.x, e.y);
                root.frame.moveBy(now.x - grabbed.x, now.y - grabbed.y, fromX, fromY);
            }
            onReleased: if (root.frame && root.frame.dragging) root.frame.endMove(fromX, fromY)
        }

        MIcon {
            id: lead
            anchors.verticalCenter: parent.verticalCenter
            icon: Icons.language
            size: 17
            color: root.busy ? Theme.c.primary : Theme.c.onSurfaceVariant
        }
        UText {
            anchors { left: lead.right; leftMargin: 8; right: tools.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
            text: root.opt("label", "") || "Request"
            size: 15; weight: Font.Medium
        }
        Row {
            id: tools
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: 2
            IconButton {
                icon: Icons.keep; size: 24; iconSize: 13
                iconColor: Theme.c.onSurfaceVariant
                onClicked: root.menuOpen = !root.menuOpen
            }
            IconButton {
                id: shut
                icon: Icons.close; size: 24; iconSize: 14
                iconColor: shut.hovered ? Theme.c.onError : Theme.c.onSurfaceVariant
                color: shut.hovered ? Theme.c.error : "transparent"
                property bool hovered: false
                onClicked: Desk.removeWidget(root.widgetId)
                HoverHandler { onHoveredChanged: shut.hovered = hovered }
            }
        }
    }

    // ---- method, address, send ----------------------------------------------------
    Row {
        id: bar
        anchors { left: parent.left; right: parent.right; margins: 12 }
        anchors { top: head.bottom; topMargin: 8 }
        spacing: 5

        Rectangle {
            width: 66; height: 34; radius: 8
            color: Theme.c.primaryContainer
            UText {
                anchors.centerIn: parent
                text: root.method
                size: 11.5; weight: Font.Medium
                color: Theme.c.onPrimaryContainer
            }
            // Cycles rather than opening a list: there are seven and you want
            // two of them.
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    var all = Api.methods();
                    root.method = all[(all.indexOf(root.method) + 1) % all.length];
                    root.keep();
                }
            }
        }
        Field {
            id: urlBox
            width: bar.width - 66 - 72 - 10
            label: "Address"
            placeholder: "api.example.com/things"
            text: root.address
            onTextChanged: { root.address = text; settle.restart(); }
            onAccepted: root.send()
        }
        Rectangle {
            width: 72; height: 34; radius: 8
            color: root.busy ? Theme.c.surfaceContainerHighest : Theme.c.primary
            UText {
                anchors.centerIn: parent
                text: root.busy ? "..." : "Send"
                size: 12; weight: Font.Medium
                color: root.busy ? Theme.c.onSurfaceVariant : Theme.c.onPrimary
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.send()
            }
        }
    }

    // ---- the two sides -------------------------------------------------------------
    Item {
        id: middle
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 12 }
        anchors { top: bar.bottom; topMargin: 8 }
        readonly property real half: (width - 8) / 2

        // ---- what you are asking ---------------------------------------------
        Rectangle {
            id: asked
            width: middle.half
            height: parent.height
            radius: 10
            color: Theme.c.surfaceContainerHighest
            clip: true

            Row {
                id: askTabs
                anchors { top: parent.top; left: parent.left; margins: 8 }
                spacing: 12
                Tab { label: "Body"; picked: root.asking === "body"; onChosen: root.asking = "body" }
                Tab { label: "Headers"; picked: root.asking === "headers"; onChosen: root.asking = "headers" }
                Tab { label: "Auth"; picked: root.asking === "auth"; onChosen: root.asking = "auth" }
            }

            // Body
            Item {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
                anchors { top: askTabs.bottom; topMargin: 6 }
                visible: root.asking === "body"

                Row {
                    id: bodyKinds
                    anchors { top: parent.top; left: parent.left }
                    spacing: 4
                    Repeater {
                        model: ["none", "json", "text", "form"]
                        Rectangle {
                            required property var modelData
                            width: kindText.implicitWidth + 14; height: 20; radius: 10
                            color: root.bodyType === modelData ? Theme.c.primary : "transparent"
                            border.width: root.bodyType === modelData ? 0 : 1
                            border.color: Theme.c.outline
                            UText {
                                id: kindText
                                anchors.centerIn: parent
                                text: modelData
                                size: 10
                                color: root.bodyType === modelData ? Theme.c.onPrimary : Theme.c.onSurfaceVariant
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { root.bodyType = modelData; root.keep(); }
                            }
                        }
                    }
                }
                UText {
                    anchors { top: bodyKinds.bottom; topMargin: 8; horizontalCenter: parent.horizontalCenter }
                    visible: !root.sendsBody
                    text: "A " + root.method + " has no body"
                    size: 11
                    color: Theme.c.onSurfaceVariant
                }
                Field {
                    id: bodyBox
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    anchors { top: bodyKinds.bottom; topMargin: 6 }
                    visible: root.sendsBody && root.bodyType !== "none"
                    label: root.bodyType === "form" ? "One name=value a line" : "Body"
                    placeholder: root.bodyType === "form" ? "name=value" : '{ "name": "value" }'
                    multiline: true
                    text: root.bodyText
                    onTextChanged: { root.bodyText = text; settle.restart(); }
                }
            }

            // Headers
            Field {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
                anchors { top: askTabs.bottom; topMargin: 6 }
                id: headerBox
                visible: root.asking === "headers"
                label: "One per line, # to skip"
                placeholder: "X-Thing: value"
                multiline: true
                text: root.headerText
                onTextChanged: { root.headerText = text; settle.restart(); }
            }

            // Auth
            Column {
                anchors { left: parent.left; right: parent.right; margins: 8 }
                anchors { top: askTabs.bottom; topMargin: 6 }
                visible: root.asking === "auth"
                spacing: 6

                Row {
                    spacing: 4
                    Repeater {
                        model: [["none", "None"], ["bearer", "Bearer"], ["basic", "Basic"], ["key", "API key"]]
                        Rectangle {
                            required property var modelData
                            width: authText.implicitWidth + 14; height: 20; radius: 10
                            color: root.authType === modelData[0] ? Theme.c.primary : "transparent"
                            border.width: root.authType === modelData[0] ? 0 : 1
                            border.color: Theme.c.outline
                            UText {
                                id: authText
                                anchors.centerIn: parent
                                text: modelData[1]
                                size: 10
                                color: root.authType === modelData[0] ? Theme.c.onPrimary : Theme.c.onSurfaceVariant
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { root.authType = modelData[0]; root.keep(); }
                            }
                        }
                    }
                }
                UText {
                    width: parent.width
                    visible: root.authType === "none"
                    wrapMode: Text.WordWrap
                    text: "Nothing is added. Anything in Headers is still sent."
                    size: 10.5
                    color: Theme.c.onSurfaceVariant
                }
                Field {
                    id: tokenBox
                    visible: root.authType === "bearer"
                    label: "Token"
                    placeholder: "sent as Authorization: Bearer ..."
                    secret: true
                    text: root.authToken
                    onTextChanged: { root.authToken = text; settle.restart(); }
                }
                Field {
                    id: userBox
                    visible: root.authType === "basic"
                    label: "User"
                    text: root.authUser
                    onTextChanged: { root.authUser = text; settle.restart(); }
                }
                Field {
                    id: passwordBox
                    visible: root.authType === "basic"
                    label: "Password"
                    secret: true
                    text: root.authPassword
                    onTextChanged: { root.authPassword = text; settle.restart(); }
                }
                Field {
                    id: keyNameBox
                    visible: root.authType === "key"
                    label: "Header name"
                    placeholder: "X-API-Key"
                    text: root.authKeyName
                    onTextChanged: { root.authKeyName = text; settle.restart(); }
                }
                Field {
                    id: keyValueBox
                    visible: root.authType === "key"
                    label: "Value"
                    secret: true
                    text: root.authKeyValue
                    onTextChanged: { root.authKeyValue = text; settle.restart(); }
                }
            }
        }

        // ---- what came back ---------------------------------------------------
        Rectangle {
            anchors { left: asked.right; leftMargin: 8; right: parent.right; top: parent.top; bottom: parent.bottom }
            radius: 10
            color: Theme.c.surfaceContainerHighest
            clip: true

            Item {
                id: verdict
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: 8 }
                height: 20

                Rectangle {
                    id: code
                    width: codeText.implicitWidth + 14; height: 18; radius: 9
                    color: root.statusColour
                    visible: root.busy || root.answer.ok !== undefined
                    UText {
                        id: codeText
                        anchors.centerIn: parent
                        text: root.busy ? "sending" : root.answer.ok ? String(root.answer.status) : "failed"
                        size: 10.5; weight: Font.Medium
                        color: Theme.c.surface
                    }
                }
                UText {
                    anchors { left: code.visible ? code.right : parent.left; leftMargin: code.visible ? 6 : 0
                              right: tabs.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                    text: root.busy ? ""
                        : root.answer.ok === undefined ? "Nothing sent yet"
                        : root.answer.ok ? (root.answer.reason || "") + "  ·  " + root.answer.ms + " ms  ·  " + root.answer.size
                        : (root.answer.error || "")
                    size: 10.5
                    color: Theme.c.onSurfaceVariant
                    elide: Text.ElideRight
                }
                Row {
                    id: tabs
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 10
                    visible: root.answer.ok === true
                    Tab { label: "Body"; picked: root.showing === "body"; onChosen: root.showing = "body" }
                    Tab { label: "Headers"; picked: root.showing === "headers"; onChosen: root.showing = "headers" }

                    // Copying is what most people do with a response next, and
                    // selecting several hundred lines by hand to do it is not
                    // a thing anybody should have to be good at.
                    UText {
                        id: copier
                        property bool just: false
                        text: copier.just ? "copied" : "copy"
                        size: 11
                        weight: copier.just ? Font.Medium : Font.Normal
                        color: copier.just ? "#5ad67d" : Theme.c.onSurfaceVariant
                        MouseArea {
                            anchors { fill: parent; margins: -4 }
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                copier.just = Api.copy(shown.text);
                                said.restart();
                            }
                        }
                        Timer { id: said; interval: 1400; onTriggered: copier.just = false }
                    }
                }
            }

            Flickable {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
                anchors { top: verdict.bottom; topMargin: 4 }
                // Measured from what the text needs, not from the box it is
                // in: binding the text's width to the box and the box to the
                // text is a loop, and Qt says so.
                contentHeight: shown.implicitHeight
                contentWidth: Math.max(shown.implicitWidth, width)
                clip: true
                TextEdit {
                    id: shown
                    readOnly: true
                    selectByMouse: true
                    font.family: "Consolas"
                    font.pixelSize: 12
                    color: Theme.c.onSurface
                    text: root.showing === "headers" ? (root.answer.headers || "") : (root.answer.body || "")
                    onActiveFocusChanged: Desk.focusInput(Window.window, activeFocus)
                }
            }
        }
    }

    // ---- the corner you pull ---------------------------------------------------------
    Item {
        width: 22; height: 22
        anchors { right: parent.right; bottom: parent.bottom }
        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: 2 + index * 4
                height: 2
                radius: 1
                color: corner.containsMouse ? Theme.c.primary : Theme.c.outline
                anchors.right: parent.right
                anchors.rightMargin: 6
                y: 14 - index * 4
                rotation: -45
                transformOrigin: Item.Right
            }
        }
        MouseArea {
            id: corner
            anchors { fill: parent; margins: -6 }
            hoverEnabled: true
            cursorShape: Qt.SizeFDiagCursor
            preventStealing: true
            property point from
            property real wasWidth
            property real wasHeight
            onPressed: (e) => {
                from = mapToItem(null, e.x, e.y);
                wasWidth = root.width;
                wasHeight = root.height;
                root.heldWidth = wasWidth;
                root.heldHeight = wasHeight;
                // While this is set the desk stops clipping itself to the
                // widgets, so what is being dragged is not cut off at the
                // size it used to be.
                if (root.frame) root.frame.sizing = true;
            }
            onPositionChanged: (e) => {
                if (!pressed) return;
                var now = mapToItem(null, e.x, e.y);
                var scale = Math.max(0.2, Theme.scale);
                root.heldWidth = Math.max(520, wasWidth + (now.x - from.x) / scale);
                root.heldHeight = Math.max(280, wasHeight + (now.y - from.y) / scale);
            }
            onReleased: {
                if (root.frame) root.frame.sizing = false;
                if (root.heldWidth <= 0) return;
                Desk.setSize(root.widgetId, Math.round(root.heldWidth), Math.round(root.heldHeight));
                root.heldWidth = 0;
                root.heldHeight = 0;
            }
        }
    }

    // ---- saved requests ----------------------------------------------------------------
    Rectangle {
        visible: root.menuOpen
        z: 60
        anchors { right: parent.right; top: head.bottom; rightMargin: 12; topMargin: 4 }
        width: 250
        height: Math.min(300, saved.height + 14)
        radius: 14
        color: Theme.c.surfaceContainerHighest
        border.width: 1
        border.color: Theme.c.outlineVariant

        Column {
            id: saved
            anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 7 }
            spacing: 2

            UText { x: 10; text: "Saved requests"; size: 10; color: Theme.c.onSurfaceVariant }
            Repeater {
                model: Api.saved
                Rectangle {
                    required property var modelData
                    width: saved.width
                    height: 28
                    color: pick.containsMouse ? Theme.c.surfaceContainerHigh : "transparent"
                    UText {
                        anchors { left: parent.left; leftMargin: 10; right: drop.left; verticalCenter: parent.verticalCenter }
                        text: (modelData.method || "GET") + "  " + modelData.name
                        size: 11
                        elide: Text.ElideRight
                    }
                    IconButton {
                        id: drop
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        visible: pick.containsMouse
                        icon: Icons.delete_; size: 20; iconSize: 11
                        iconColor: Theme.c.onSurfaceVariant
                        onClicked: Api.forget(modelData.name)
                    }
                    MouseArea {
                        id: pick
                        anchors { fill: parent; rightMargin: 22 }
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { root.fill(Api.recall(modelData.name)); root.keep(); root.menuOpen = false; }
                    }
                }
            }
            Item { width: 1; height: 6 }
            Field {
                id: nameBox
                x: 10
                width: saved.width - 20
                label: "Call it"
                placeholder: root.address
            }
            Item { width: 1; height: 5 }
            Row {
                x: 10
                spacing: 5
                Pill {
                    label: "Save this one"
                    filled: true
                    onPressed: {
                        var name = nameBox.text.trim() || root.address;
                        if (name === "") return;
                        Api.remember(name, root.request());
                        nameBox.text = "";
                        root.menuOpen = false;
                    }
                }
            }
            Item { width: 1; height: 6 }
        }
    }
    MouseArea {
        anchors.fill: parent
        visible: root.menuOpen
        z: 55
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: root.menuOpen = false
    }

    // A heading you can click, underlined while it is the one showing.
    component Tab: Item {
        id: tab
        property string label: ""
        property bool picked: false
        signal chosen()
        width: tabText.implicitWidth
        height: 16
        UText {
            id: tabText
            text: tab.label
            size: 11
            weight: tab.picked ? Font.Medium : Font.Normal
            color: tab.picked ? Theme.c.primary : Theme.c.onSurfaceVariant
        }
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 2
            radius: 1
            color: Theme.c.primary
            visible: tab.picked
        }
        MouseArea {
            anchors { fill: parent; margins: -4 }
            cursorShape: Qt.PointingHandCursor
            onClicked: tab.chosen()
        }
    }
}
