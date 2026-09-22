import QtQuick
import QtQuick.Effects
import "components"
import "Icons.js" as Icons

// Start: the Windows 11 menu, laid out the same way and drawn in the desk's
// theme. A search box, a page of pinned apps with dots down the side, what you
// opened lately, and your name beside the power button.
//
// Three views live in the body: the home page, all apps, and search results,
// which take over the moment you type. Esc steps back out of whichever one you
// are in, and then closes.
Item {
    id: panel
    width: 640
    height: 724

    property string view: "home"        // home | all | more
    property int page: 0
    property int current: 0             // the highlighted search result
    readonly property var pins: Start.pinned
    readonly property var rows: Start.recommended
    readonly property bool searching: input.text.length > 0
    readonly property real pad: 28
    readonly property real gridWidth: width - pad * 2 - 22
    readonly property real tile: gridWidth / 6

    signal closed()

    function reset() {
        view = "home";
        page = 0;
        current = 0;
        input.text = "";
        Search.setQuery("");
        menu.hide();
        powerMenu.open = false;
        accountMenu.open = false;
    }
    function focusInput() { input.forceActiveFocus(); input.selectAll(); }
    function back() {
        if (menu.shown) { menu.hide(); return true; }
        if (powerMenu.open || accountMenu.open) { powerMenu.open = false; accountMenu.open = false; return true; }
        if (searching) { input.text = ""; Search.setQuery(""); return true; }
        if (view !== "home") { view = "home"; return true; }
        return false;
    }
    function openSelected() {
        if (Search.activate(current)) { Start.setOpen(false); }
    }
    function run(appid) { if (Start.launch(appid)) Start.setOpen(false); }

    // Everything the three menus can ask for. Menu rows carry the name of what
    // they do rather than a function, so a model row stays plain data - and so
    // a test can ask for one by name.
    function act(what) {
        var appid = menu.app.appid;
        if (what === "unpin") Start.unpin(appid);
        else if (what === "front") { Start.moveToFront(appid); page = 0; }
        else if (what === "pin") Start.pin(appid, menu.app.name);
        else if (what === "where") { Start.openLocation(appid); Start.setOpen(false); }
        else if (what === "admin") { Start.runAsAdmin(appid); Start.setOpen(false); }
        else if (what === "uninstall") { Start.uninstall(appid); Start.setOpen(false); }
        else if (what === "account") { Start.accountSettings(); Start.setOpen(false); }
        else Start.power(what);   // lock, signout, sleep, restart, shutdown
    }
    function openFile(target) { if (Start.openPath(target)) Start.setOpen(false); }

    onSearchingChanged: current = 0
    Connections {
        target: Search
        function onResultsChanged() { panel.current = 0; }
    }
    // A page that no longer exists (the last pin on it was unpinned).
    onPinsChanged: if (page >= Start.pages) page = Math.max(0, Start.pages - 1)

    RectangularShadow {
        anchors.fill: bg
        radius: bg.radius
        blur: 40; spread: -2; offset.y: 10
        color: Qt.rgba(0, 0, 0, 0.5)
        visible: Theme.shadows
    }
    Rectangle {
        id: bg
        anchors.fill: parent
        radius: 30
        color: Theme.c.surfaceContainer
        border.width: 1
        border.color: Qt.alpha(Theme.c.outlineVariant, 0.6)
    }

    // ---- one app's icon --------------------------------------------------------------
    // Rows carry a key, not a picture: the icon is asked for when it is on
    // screen, and iconRevision is what brings the answer back.
    component AppIcon: Item {
        id: art
        property string key: ""
        property string glyph: "apps"
        property real size: 36
        readonly property string url: Start.iconRevision >= 0 ? Start.iconFor(key) : ""
        width: size; height: size

        Image {
            anchors.fill: parent
            visible: art.url !== ""
            source: art.url
            sourceSize: Qt.size(art.size * 2, art.size * 2)
            smooth: true; mipmap: true
            asynchronous: true
        }
        MShape {
            anchors.fill: parent
            visible: art.url === ""
            shape: "cookie12"
            color: Theme.c.primaryContainer
        }
        MIcon {
            anchors.centerIn: parent
            visible: art.url === ""
            icon: Icons[art.glyph] || Icons.apps
            size: art.size * 0.5
            fill: 1
            color: Theme.c.onPrimaryContainer
        }
    }

    // ---- a heading with a way further in ---------------------------------------------
    // The label wears the blue off the dock's clock; the way further in is a
    // filled tonal button, the same treatment as the CPU and RAM tiles - which
    // is where its tone comes from: primary for the first section, secondary
    // for the second, exactly as those two widgets are set up.
    component Heading: Item {
        id: head
        property string label: ""
        property string action: ""
        property string tone: "primary"
        readonly property color toneBack: ({
            primary: Theme.c.primaryContainer, secondary: Theme.c.secondaryContainer, tertiary: Theme.c.tertiaryContainer
        })[tone] || Theme.c.primaryContainer
        readonly property color toneInk: ({
            primary: Theme.c.onPrimaryContainer, secondary: Theme.c.onSecondaryContainer, tertiary: Theme.c.onTertiaryContainer
        })[tone] || Theme.c.onPrimaryContainer
        signal pressed()
        width: panel.width - panel.pad * 2
        height: 36

        UText {
            anchors.verticalCenter: parent.verticalCenter
            text: head.label
            size: 14
            weight: Font.DemiBold
            color: Theme.c.onPrimaryContainer
        }
        Rectangle {
            id: more
            visible: head.action !== ""
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            width: moreRow.width + 26
            height: 30
            radius: 15
            color: head.toneBack
            scale: moreMouse.pressed ? 0.96 : 1
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: 400 } }

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: head.toneInk
                opacity: moreMouse.pressed ? 0.16 : moreMouse.containsMouse ? 0.09 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }
            Row {
                id: moreRow
                anchors.centerIn: parent
                spacing: 1
                UText {
                    anchors.verticalCenter: parent.verticalCenter
                    text: head.action
                    size: 12.5
                    weight: Font.Medium
                    color: head.toneInk
                }
                MIcon {
                    anchors.verticalCenter: parent.verticalCenter
                    icon: Icons.chevron_right
                    rotation: head.action === "Back" ? 180 : 0
                    size: 17
                    color: head.toneInk
                }
            }
            MouseArea {
                id: moreMouse
                anchors { fill: parent; margins: -4 }
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: head.pressed()
            }
        }
    }

    // ---- the search box --------------------------------------------------------------
    Rectangle {
        id: box
        x: panel.pad; y: 20
        width: parent.width - panel.pad * 2
        height: 52
        radius: 26
        color: Theme.c.surfaceContainerHighest
        border.width: input.activeFocus ? 1.5 : 0
        border.color: Theme.c.primary

        MIcon {
            id: glass
            x: 18
            anchors.verticalCenter: parent.verticalCenter
            icon: Icons.search
            size: 22
            color: Theme.c.primary
        }
        TextInput {
            id: input
            objectName: "startSearch"
            anchors { left: glass.right; leftMargin: 12; right: parent.right; rightMargin: 18; verticalCenter: parent.verticalCenter }
            font.family: Theme.font
            font.pixelSize: 17
            color: Theme.c.onSurface
            selectionColor: Theme.c.primary
            selectedTextColor: Theme.c.onPrimary
            clip: true
            onTextChanged: Search.setQuery(text)
            Keys.onPressed: (e) => {
                if (e.key === Qt.Key_Down) {
                    if (panel.searching) panel.current = Math.min(Search.results.length - 1, panel.current + 1);
                    e.accepted = true;
                } else if (e.key === Qt.Key_Up) {
                    if (panel.searching) panel.current = Math.max(0, panel.current - 1);
                    e.accepted = true;
                } else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter) {
                    if (panel.searching) panel.openSelected();
                    e.accepted = true;
                } else if (e.key === Qt.Key_Escape) {
                    if (!panel.back()) Start.setOpen(false);
                    e.accepted = true;
                }
            }
            UText {
                visible: input.text === ""
                anchors.verticalCenter: parent.verticalCenter
                text: "Search for apps, settings, and documents"
                size: 15.5
                color: Theme.c.onSurfaceVariant
            }
        }
    }

    // ---- the body ---------------------------------------------------------------------
    Item {
        id: body
        anchors { left: parent.left; right: parent.right; top: box.bottom; topMargin: 18; bottom: footer.top; bottomMargin: 8 }

        // home: pinned, then what you opened lately
        Item {
            anchors.fill: parent
            visible: opacity > 0
            opacity: panel.view === "home" && !panel.searching ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 130 } }

            Heading {
                id: pinnedHead
                objectName: "pinnedHeading"
                x: panel.pad
                label: "Pinned"
                action: "All apps"
                tone: "primary"
                onPressed: panel.view = "all"
            }

            Item {
                id: gridArea
                objectName: "pinGrid"
                anchors { top: pinnedHead.bottom; topMargin: 2; left: parent.left; leftMargin: panel.pad }
                width: panel.gridWidth
                height: panel.tile * 3

                Grid {
                    id: grid
                    width: parent.width
                    columns: 6
                    Repeater {
                        model: Math.min(Start.perPage, Math.max(0, panel.pins.length - panel.page * Start.perPage))
                        delegate: Item {
                            id: cell
                            required property int index
                            objectName: "pin" + index
                            readonly property int at: panel.page * Start.perPage + index
                            readonly property var app: panel.pins[at] || ({ name: "", appid: "", key: "" })
                            width: panel.tile
                            height: panel.tile

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 3
                                radius: 16
                                color: Theme.c.onSurface
                                opacity: cellMouse.pressed ? 0.14 : cellMouse.containsMouse ? 0.07 : 0
                                Behavior on opacity { NumberAnimation { duration: 110 } }
                            }
                            AppIcon {
                                id: cellIcon
                                key: cell.app.key
                                size: 36
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: 14
                                scale: cellMouse.pressed ? 0.92 : 1
                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                            }
                            UText {
                                anchors { top: cellIcon.bottom; topMargin: 8; left: parent.left; right: parent.right; margins: 6 }
                                text: cell.app.name
                                size: 11.5
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                color: Theme.c.onSurface
                            }
                            MouseArea {
                                id: cellMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: (e) => {
                                    if (e.button === Qt.RightButton) menu.show(cell, cell.app, true);
                                    else panel.run(cell.app.appid);
                                }
                            }
                        }
                    }
                }
                // Turn the page with the wheel, as the real one does.
                WheelHandler {
                    onWheel: (e) => {
                        if (Start.pages < 2) return;
                        panel.page = Math.max(0, Math.min(Start.pages - 1, panel.page + (e.angleDelta.y < 0 ? 1 : -1)));
                    }
                }
                UText {
                    anchors.centerIn: parent
                    visible: panel.pins.length === 0
                    text: Start.iconRevision >= 0 && Search.indexing ? "Finding your apps…" : "Nothing pinned yet — open All apps and pin something"
                    size: 13
                    color: Theme.c.onSurfaceVariant
                }
            }

            // which page of pins you are on
            Column {
                anchors { left: gridArea.right; leftMargin: 6; verticalCenter: gridArea.verticalCenter }
                spacing: 6
                visible: Start.pages > 1
                Repeater {
                    model: Start.pages
                    delegate: Rectangle {
                        required property int index
                        width: 5
                        height: index === panel.page ? 18 : 5
                        radius: 2.5
                        color: index === panel.page ? Theme.c.primary : Theme.c.onSurfaceVariant
                        opacity: index === panel.page ? 1 : 0.4
                        Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        MouseArea {
                            anchors { fill: parent; margins: -6 }
                            cursorShape: Qt.PointingHandCursor
                            onClicked: panel.page = parent.index
                        }
                    }
                }
            }

            Heading {
                id: recHead
                x: panel.pad
                anchors { top: gridArea.bottom; topMargin: 16 }
                label: "Recommended"
                action: panel.rows.length > 0 ? "More" : ""
                tone: "secondary"
                onPressed: panel.view = "more"
            }

            Grid {
                anchors { top: recHead.bottom; topMargin: 2; left: parent.left; leftMargin: panel.pad }
                width: panel.width - panel.pad * 2
                columns: 2
                Repeater {
                    model: panel.rows
                    delegate: RecentRow {
                        required property var modelData
                        row: modelData
                        width: (panel.width - panel.pad * 2) / 2
                    }
                }
            }
            UText {
                anchors { top: recHead.bottom; topMargin: 14; left: parent.left; leftMargin: panel.pad + 4 }
                visible: panel.rows.length === 0
                text: "Nothing yet — what you open will show up here"
                size: 13
                color: Theme.c.onSurfaceVariant
            }
        }

        // all apps, under the letter they start with
        Item {
            anchors.fill: parent
            visible: opacity > 0
            opacity: panel.view === "all" && !panel.searching ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 130 } }

            Heading {
                id: allHead
                objectName: "allHeading"
                x: panel.pad
                label: "All apps"
                action: "Back"
                tone: "primary"
                onPressed: panel.view = "home"
            }
            ListView {
                id: allList
                anchors { top: allHead.bottom; topMargin: 4; left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: panel.pad; rightMargin: panel.pad - 8 }
                clip: true
                model: panel.view === "all" ? Start.apps : []
                spacing: 1
                boundsBehavior: Flickable.StopAtBounds
                section.property: "section"
                section.delegate: UText {
                    required property string section
                    width: allList.width
                    leftPadding: 12; topPadding: 10; bottomPadding: 2
                    text: section
                    size: 13
                    weight: Font.DemiBold
                    color: Theme.c.onPrimaryContainer
                }
                delegate: Item {
                    id: appRow
                    required property var modelData
                    width: ListView.view.width
                    height: 46

                    Rectangle {
                        anchors { fill: parent; rightMargin: 6 }
                        radius: 14
                        color: Theme.c.onSurface
                        opacity: appMouse.pressed ? 0.14 : appMouse.containsMouse ? 0.07 : 0
                        Behavior on opacity { NumberAnimation { duration: 110 } }
                    }
                    AppIcon {
                        id: rowIcon
                        x: 12
                        anchors.verticalCenter: parent.verticalCenter
                        key: appRow.modelData.key
                        size: 26
                    }
                    UText {
                        anchors { left: rowIcon.right; leftMargin: 14; right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                        text: appRow.modelData.name
                        size: 14
                        color: Theme.c.onSurface
                    }
                    MouseArea {
                        id: appMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onClicked: (e) => {
                            if (e.button === Qt.RightButton) menu.show(appRow, appRow.modelData, false);
                            else panel.run(appRow.modelData.appid);
                        }
                    }
                }
            }
        }

        // everything Recommended has room for
        Item {
            anchors.fill: parent
            visible: opacity > 0
            opacity: panel.view === "more" && !panel.searching ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 130 } }

            Heading {
                id: moreHead
                objectName: "moreHeading"
                x: panel.pad
                label: "Recommended"
                action: "Back"
                tone: "secondary"
                onPressed: panel.view = "home"
            }
            ListView {
                anchors { top: moreHead.bottom; topMargin: 4; left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: panel.pad; rightMargin: panel.pad - 8 }
                clip: true
                model: panel.view === "more" ? Start.history : []
                spacing: 1
                boundsBehavior: Flickable.StopAtBounds
                delegate: RecentRow {
                    required property var modelData
                    row: modelData
                    width: ListView.view.width - 6
                }
            }
        }

        // what you typed
        Item {
            anchors.fill: parent
            visible: opacity > 0
            opacity: panel.searching ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 130 } }

            ListView {
                id: found
                anchors { fill: parent; leftMargin: panel.pad; rightMargin: panel.pad - 8 }
                clip: true
                model: panel.searching ? Search.results : []
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                currentIndex: panel.current
                highlightMoveDuration: 140
                onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)
                section.property: "section"
                section.delegate: UText {
                    required property string section
                    width: found.width
                    leftPadding: 12; topPadding: 10; bottomPadding: 2
                    text: section
                    size: 12.5
                    weight: Font.DemiBold
                    color: Theme.c.onPrimaryContainer
                }
                delegate: Item {
                    id: hit
                    required property var modelData
                    required property int index
                    readonly property bool selected: panel.current === index
                    width: ListView.view.width
                    height: 52

                    Rectangle {
                        anchors { fill: parent; rightMargin: 6 }
                        radius: 16
                        color: hit.selected ? Theme.c.secondaryContainer : Theme.c.onSurface
                        opacity: hit.selected ? 1 : hitMouse.containsMouse ? 0.06 : 0
                        Behavior on opacity { NumberAnimation { duration: 110 } }
                    }
                    Item {
                        id: hitIcon
                        x: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: 30; height: 30
                        Image {
                            anchors.fill: parent
                            visible: hit.modelData.icon !== ""
                            source: hit.modelData.icon
                            sourceSize: Qt.size(60, 60)
                            smooth: true; mipmap: true
                            asynchronous: true
                        }
                        MShape {
                            anchors.fill: parent
                            visible: hit.modelData.icon === ""
                            shape: "cookie12"
                            color: hit.selected ? Theme.c.primary : Theme.c.primaryContainer
                        }
                        MIcon {
                            anchors.centerIn: parent
                            visible: hit.modelData.icon === ""
                            icon: Icons[hit.modelData.glyph || "search"] || Icons.search
                            size: 16
                            fill: 1
                            color: hit.selected ? Theme.c.onPrimary : Theme.c.onPrimaryContainer
                        }
                    }
                    Column {
                        anchors { left: hitIcon.right; leftMargin: 14; right: parent.right; rightMargin: 18; verticalCenter: parent.verticalCenter }
                        UText {
                            width: parent.width
                            text: hit.modelData.title
                            size: hit.modelData.kind === "calc" ? 19 : 14.5
                            weight: hit.modelData.kind === "calc" ? Font.DemiBold : Font.Medium
                            color: hit.selected ? Theme.c.onSecondaryContainer : Theme.c.onSurface
                        }
                        UText {
                            width: parent.width
                            text: hit.modelData.subtitle
                            size: 11.5
                            color: hit.selected ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant
                            opacity: 0.85
                        }
                    }
                    MouseArea {
                        id: hitMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: panel.current = hit.index
                        onClicked: panel.openSelected()
                    }
                }
            }
            UText {
                anchors.centerIn: parent
                visible: found.count === 0
                text: "Nothing matches that"
                size: 13
                color: Theme.c.onSurfaceVariant
            }
        }
    }

    // one line of Recommended: an app that turned up, or a file you opened
    component RecentRow: Item {
        id: line
        property var row: ({ title: "", subtitle: "", kind: "file", key: "", target: "" })
        height: 56

        Rectangle {
            anchors { fill: parent; margins: 2 }
            radius: 14
            color: Theme.c.onSurface
            opacity: lineMouse.pressed ? 0.14 : lineMouse.containsMouse ? 0.07 : 0
            Behavior on opacity { NumberAnimation { duration: 110 } }
        }
        AppIcon {
            id: lineIcon
            x: 12
            anchors.verticalCenter: parent.verticalCenter
            key: line.row.key
            glyph: line.row.kind === "app" ? "apps" : "description"
            size: 28
        }
        Column {
            anchors { left: lineIcon.right; leftMargin: 12; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
            spacing: 1
            UText {
                width: parent.width
                text: line.row.title
                size: 13.5
                weight: Font.Medium
                color: Theme.c.onSurface
            }
            UText {
                width: parent.width
                text: line.row.subtitle
                size: 11.5
                color: Theme.c.onSurfaceVariant
            }
        }
        MouseArea {
            id: lineMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: line.row.kind === "app" ? panel.run(line.row.target) : panel.openFile(line.row.target)
        }
    }

    // ---- your name and the power button ------------------------------------------------
    Item {
        id: footer
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 70

        Rectangle {
            anchors.fill: parent
            radius: 30
            color: Theme.c.surfaceContainerHighest
            opacity: 0.6
            // square off the top two corners, so only the panel's own corners round
            Rectangle {
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: parent.radius
                color: parent.color
            }
        }
        Rectangle {
            anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: panel.pad; rightMargin: panel.pad }
            height: 1
            color: Qt.alpha(Theme.c.outlineVariant, 0.5)
        }

        // you
        Item {
            id: account
            objectName: "accountButton"
            x: panel.pad - 8
            anchors.verticalCenter: parent.verticalCenter
            width: who.width + face.width + 26
            height: 46

            Rectangle {
                anchors.fill: parent
                radius: 23
                color: Theme.c.onSurface
                opacity: accountMouse.containsMouse ? 0.07 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }
            Item {
                id: face
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                width: 32; height: 32
                Rectangle {
                    anchors.fill: parent
                    radius: width / 2
                    color: Theme.c.primaryContainer
                    visible: !picture.visible || !picture.ready
                }
                UText {
                    anchors.centerIn: parent
                    visible: !picture.visible || !picture.ready
                    text: (Start.user.initials || "?")
                    size: 12.5
                    weight: Font.DemiBold
                    color: Theme.c.onPrimaryContainer
                }
                ShapedImage {
                    id: picture
                    anchors.fill: parent
                    visible: (Start.user.picture || "") !== ""
                    radius: width / 2
                    source: Start.user.picture || ""
                }
            }
            UText {
                id: who
                anchors { left: face.right; leftMargin: 10; verticalCenter: parent.verticalCenter }
                text: Start.user.name || "You"
                size: 13.5
                weight: Font.Medium
                color: Theme.c.onSurface
            }
            MouseArea {
                id: accountMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { powerMenu.open = false; accountMenu.open = !accountMenu.open; }
            }
        }

        IconButton {
            id: powerButton
            objectName: "powerButton"
            anchors { right: parent.right; rightMargin: panel.pad - 6; verticalCenter: parent.verticalCenter }
            icon: Icons.power_settings_new
            size: 42
            iconSize: 21
            iconColor: Theme.c.onSurface
            onClicked: { accountMenu.open = false; powerMenu.open = !powerMenu.open; }
        }
    }

    // ---- the two small menus in the footer ---------------------------------------------
    component SmallMenu: Item {
        id: small
        property bool open: false
        property var entries: []
        visible: opacity > 0
        opacity: open ? 1 : 0
        scale: open ? 1 : 0.96
        transformOrigin: Item.Bottom
        width: 240
        height: column.height + 12
        z: 11
        Behavior on opacity { NumberAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.fill: parent
            radius: 18
            color: Theme.c.surfaceContainerHighest
            border.width: 1
            border.color: Qt.alpha(Theme.c.outlineVariant, 0.6)
        }
        Column {
            id: column
            y: 6
            width: parent.width
            Repeater {
                model: small.entries
                delegate: Item {
                    id: entry
                    required property var modelData
                    width: column.width
                    height: 40

                    Rectangle {
                        anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                        radius: 12
                        color: Theme.c.onSurface
                        opacity: entryMouse.containsMouse ? 0.08 : 0
                    }
                    MIcon {
                        id: entryIcon
                        x: 18
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons[entry.modelData.glyph] || Icons.settings
                        size: 19
                        color: Theme.c.onSurfaceVariant
                    }
                    UText {
                        anchors { left: entryIcon.right; leftMargin: 14; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                        text: entry.modelData.label
                        size: 13.5
                        color: Theme.c.onSurface
                    }
                    MouseArea {
                        id: entryMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { small.open = false; panel.act(entry.modelData.key); }
                    }
                }
            }
        }
    }

    SmallMenu {
        id: accountMenu
        objectName: "accountMenu"
        x: panel.pad - 8
        y: footer.y - height - 6
        entries: [
            { label: "Change account settings", glyph: "settings", key: "account" },
            { label: "Sign out", glyph: "logout", key: "signout" }
        ]
    }
    SmallMenu {
        id: powerMenu
        objectName: "powerMenu"
        x: panel.width - width - panel.pad + 6
        y: footer.y - height - 6
        entries: [
            { label: "Lock", glyph: "lock", key: "lock" },
            { label: "Sleep", glyph: "bedtime", key: "sleep" },
            { label: "Restart", glyph: "restart_alt", key: "restart" },
            { label: "Shut down", glyph: "power_settings_new", key: "shutdown" }
        ]
    }

    // ---- right-click on an app ----------------------------------------------------------
    Item {
        id: menu
        objectName: "appMenu"
        property bool shown: false
        property var app: ({ name: "", appid: "" })
        property bool pinnedHere: false
        visible: opacity > 0
        opacity: shown ? 1 : 0
        scale: shown ? 1 : 0.96
        width: 234
        height: menuColumn.height + 12
        z: 10
        Behavior on opacity { NumberAnimation { duration: 110 } }
        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

        function show(item, app, isPinned) {
            menu.app = app;
            menu.pinnedHere = isPinned;
            var where = item.mapToItem(panel, 0, 0);
            menu.x = Math.max(8, Math.min(panel.width - menu.width - 8, where.x + 12));
            menu.y = Math.max(8, Math.min(panel.height - menu.height - 8, where.y + 30));
            menu.shown = true;
        }
        function hide() { menu.shown = false; }

        readonly property var entries: {
            var rows = [];
            if (pinnedHere) {
                rows.push({ label: "Unpin from Start", glyph: "push_pin", key: "unpin" });
                rows.push({ label: "Move to front", glyph: "arrow_upward", key: "front" });
            } else {
                rows.push({ label: "Pin to Start", glyph: "push_pin", key: "pin" });
            }
            rows.push({ label: "Open file location", glyph: "folder", key: "where" });
            if (Start.canRunAsAdmin(app.appid))
                rows.push({ label: "Run as administrator", glyph: "lock", key: "admin" });
            rows.push({ label: "Uninstall", glyph: "delete_", key: "uninstall" });
            return rows;
        }

        RectangularShadow {
            anchors.fill: menuBg
            radius: menuBg.radius
            blur: 24; spread: -2; offset.y: 6
            color: Qt.rgba(0, 0, 0, 0.4)
            visible: Theme.shadows
        }
        Rectangle {
            id: menuBg
            anchors.fill: parent
            radius: 18
            color: Theme.c.surfaceContainerHighest
            border.width: 1
            border.color: Qt.alpha(Theme.c.outlineVariant, 0.6)
        }
        Column {
            id: menuColumn
            y: 6
            width: parent.width
            Repeater {
                model: menu.entries
                delegate: Item {
                    id: menuRow
                    required property var modelData
                    width: menuColumn.width
                    height: 40

                    Rectangle {
                        anchors { fill: parent; leftMargin: 6; rightMargin: 6 }
                        radius: 12
                        color: Theme.c.onSurface
                        opacity: menuRowMouse.containsMouse ? 0.08 : 0
                    }
                    MIcon {
                        id: menuIcon
                        x: 18
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons[menuRow.modelData.glyph] || Icons.settings
                        size: 19
                        color: Theme.c.onSurfaceVariant
                    }
                    UText {
                        anchors { left: menuIcon.right; leftMargin: 14; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                        text: menuRow.modelData.label
                        size: 13.5
                        color: Theme.c.onSurface
                    }
                    MouseArea {
                        id: menuRowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { menu.hide(); panel.act(menuRow.modelData.key); }
                    }
                }
            }
        }
    }

    // Clicking anywhere else puts the menus away, without swallowing the click
    // that opened one.
    MouseArea {
        anchors.fill: parent
        z: 9
        visible: menu.shown || powerMenu.open || accountMenu.open
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: { menu.hide(); powerMenu.open = false; accountMenu.open = false; }
    }
}
