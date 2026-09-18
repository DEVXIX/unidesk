import QtQuick
import QtQuick.Effects
import QtQuick.Window
import "components"
import "Icons.js" as Icons

// The dock: a floating pill at the bottom centre with now playing, Start,
// search, your apps (soft zoom on hover), the tray button, quick icons and the
// clock. One per screen. The window spans the bottom of its screen but is
// clipped to the pill and whatever popup is open, so everything else stays
// clickable.
Window {
    id: dockWin
    required property QtObject slot
    // No Qt.WindowDoesNotAcceptFocus: the dock is made non-activating natively,
    // and allowed to take the keyboard only while search is open.
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
    color: "transparent"
    title: "unidesk dock"
    readonly property var cfg: Desk.dock
    readonly property real iconSize: cfg.icon_size || 40
    readonly property real zoom: cfg.zoom === undefined ? 1.3 : cfg.zoom
    readonly property real pillHeight: iconSize + 16
    readonly property real bottomGap: 8
    readonly property bool searchHere: Search.open && Search.screen === slot.number

    screen: {
        var all = Qt.application.screens;
        for (var i = 0; i < all.length; i++) if (all[i].name === slot.name) return all[i];
        return all[0];
    }
    x: slot.rect.x
    width: slot.rect.width
    height: 700
    y: slot.rect.y + slot.rect.height - height
    // Shown once it is set up (on top, not taking focus, clipped). Hidden while
    // a fullscreen app covers its screen, unless search was opened here.
    property bool ready: false
    visible: ready && cfg.enabled !== false && (!slot.suspended || searchHere)
    onPillHeightChanged: Dock.reserve(dockWin, pillHeight + bottomGap * 2)

    // Every app, or with "apps: screen" only those with a window on this screen (pins always stay).
    readonly property string monitor: cfg.apps === "screen" ? slot.name : ""
    readonly property var apps: {
        var list = Dock.apps;
        if (!monitor) return list;
        var out = [];
        for (var i = 0; i < list.length; i++) {
            var app = list[i], wins = [], active = false;
            for (var j = 0; j < app.windows.length; j++) {
                if (app.windows[j].monitor !== monitor) continue;
                wins.push(app.windows[j]);
                active = active || app.windows[j].active;
            }
            if (!app.pinned && wins.length === 0) continue;
            out.push(Object.assign({}, app, { windows: wins, running: wins.length > 0, active: active }));
        }
        return out;
    }

    // drag-to-reorder state (pinned apps only)
    property int dragIndex: -1
    property int dragTarget: -1
    property real dragOffset: 0
    readonly property real slotWidth: iconSize + 14
    readonly property int pinnedCount: {
        var n = 0, list = dockWin.apps;
        for (var i = 0; i < list.length; i++) if (list[i].pinned) n++;
        return n;
    }

    property int hovered: -1
    property var menuApp: null
    // read once when the menu opens: it goes to the shell and to disk, so it is
    // not something to re-evaluate on every repaint
    property var jumpRows: []
    onMenuAppChanged: jumpRows = menuApp ? Dock.jumpList(menuApp.key) : []
    property string pickerKey: ""
    property real pickerX: 0
    readonly property var pickerApp: {
        var list = dockWin.apps;
        for (var i = 0; i < list.length; i++) if (list[i].key === pickerKey) return list[i];
        return null;
    }
    property real menuX: 0
    property bool playerOpen: false
    property date now: new Date()

    Timer {
        running: dockWin.visible
        repeat: false
        interval: dockWin.cfg.clock_seconds ? 1000 - new Date().getMilliseconds() : 60000 - (new Date().getSeconds() * 1000 + new Date().getMilliseconds())
        onTriggered: { dockWin.now = new Date(); restart(); }
    }

    // ---- clipping ----------------------------------------------------------------
    function updateMask() {
        var rects = [];
        var top = pill.y - (hovered >= 0 ? iconSize * (zoom - 1) + 44 : 6);
        rects.push([pill.x - 8, top, pill.width + 16, height - top]);
        if (menu.visible) rects.push([menu.x - 20, menu.y - 20, menu.width + 40, menu.height + 40]);
        if (picker.visible) rects.push([picker.x - 24, picker.y - 24, picker.width + 48, picker.height + 48]);
        if (player.visible) rects.push([player.x - 24, player.y - 24, player.width + 48, player.height + 48]);
        if (search.visible) rects.push([search.x - 40, search.y - 40, search.width + 80, search.height + 60]);
        Desk.setMask(dockWin, rects);
    }
    Timer { id: maskTimer; interval: 16; onTriggered: dockWin.updateMask() }
    onHoveredChanged: maskTimer.restart()
    onVisibleChanged: if (visible) { Dock.registerWindow(dockWin); Dock.reserve(dockWin, pillHeight + bottomGap * 2); maskTimer.restart(); }
    Component.onCompleted: {
        Dock.registerWindow(dockWin);
        if (cfg.enabled !== false) Dock.reserve(dockWin, pillHeight + bottomGap * 2);
        updateMask();
        ready = true;
    }

    // Close popups when the pointer has left them for a moment.
    Timer {
        id: closeTimer
        interval: 900
        onTriggered: { dockWin.menuApp = null; dockWin.playerOpen = false; dockWin.pickerKey = ""; maskTimer.restart(); }
    }
    function keepPopups() { closeTimer.stop(); }
    function releasePopups() { if (menu.visible || player.visible || picker.visible) closeTimer.restart(); }

    // ---- the pill ------------------------------------------------------------------
    Item {
        id: pill
        width: content.width + 20
        height: dockWin.pillHeight
        x: Math.round((dockWin.width - width) / 2)
        y: dockWin.height - height - dockWin.bottomGap
        Behavior on width { NumberAnimation { duration: 220 * Theme.animationSpeed; easing.type: Easing.OutCubic } }
        onWidthChanged: maskTimer.restart()

        RectangularShadow {
            anchors.fill: bg
            radius: bg.radius
            blur: 24; spread: -2; offset.y: 4
            color: Qt.rgba(0, 0, 0, 0.35)
            visible: Theme.shadows
        }
        Rectangle {
            id: bg
            anchors.fill: parent
            radius: height / 2
            color: Theme.c.surfaceContainer
            opacity: Math.max(0.86, Theme.cardOpacity)
            border.width: 1
            border.color: Qt.alpha(Theme.c.outlineVariant, 0.5)
            Behavior on color { ColorAnimation { duration: 600 } }
        }

        HoverHandler { onHoveredChanged: hovered ? dockWin.keepPopups() : dockWin.releasePopups() }

        Row {
            id: content
            x: 10
            height: parent.height
            spacing: 6

            // now playing
            Item {
                id: nowPlaying
                visible: dockWin.cfg.now_playing !== false && !!Media.playing
                width: visible ? npRow.width + 16 : 0
                height: parent.height
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 6; anchors.bottomMargin: 6
                    radius: height / 2
                    color: dockWin.playerOpen ? Theme.c.secondaryContainer : Theme.c.onSurface
                    opacity: dockWin.playerOpen ? 1 : npMouse.containsMouse ? 0.08 : 0
                }
                Row {
                    id: npRow
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    ShapedImage {
                        width: dockWin.iconSize - 4; height: width
                        radius: width / 2
                        anchors.verticalCenter: parent.verticalCenter
                        source: Media.playing && Media.playing.art ? Media.playing.art : ""
                        rotation: Media.playing && Media.playing.status === "playing" ? 0 : 0
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(170, Math.max(npTitle.implicitWidth, npArtist.implicitWidth))
                        UText { id: npTitle; width: parent.width; text: Media.playing ? Media.playing.title : ""; size: 13.5; weight: Font.Medium }
                        UText { id: npArtist; width: parent.width; text: Media.playing ? Media.playing.artist : ""; size: 12; color: Theme.c.onSurfaceVariant }
                    }
                }
                MouseArea {
                    id: npMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                    cursorShape: Qt.PointingHandCursor
                    onClicked: (e) => {
                        if (e.button === Qt.MiddleButton) { Media.playPause(); return; }
                        dockWin.menuApp = null;
                        dockWin.playerOpen = !dockWin.playerOpen;
                        maskTimer.restart();
                    }
                    onWheel: (w) => w.angleDelta.y < 0 ? Media.next() : Media.previous()
                }
            }
            Separator { visible: nowPlaying.visible }

            // Start
            DockButton {
                onClicked: Dock.openStart()
                Grid {
                    anchors.centerIn: parent
                    columns: 2; spacing: 2
                    Repeater {
                        model: 4
                        Rectangle { width: dockWin.iconSize * 0.24; height: width; radius: width * 0.25; color: Theme.c.primary }
                    }
                }
            }

            // Search
            Item {
                visible: dockWin.cfg.search !== false
                width: visible ? 150 : 0
                height: parent.height
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 9; anchors.bottomMargin: 9
                    radius: height / 2
                    color: Theme.c.surfaceContainerHighest
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 12; spacing: 8
                        MIcon { icon: Icons.search; size: 19; color: Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
                        UText { text: "Search"; size: 14; color: Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Rectangle { anchors.fill: parent; radius: parent.radius; color: Theme.c.onSurface; opacity: searchMouse.containsMouse ? 0.06 : 0 }
                    MouseArea {
                        id: searchMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: (Desk.config.search || {}).enabled === false ? Dock.openSearch() : Search.toggleOn(dockWin.slot.number)
                    }
                }
            }

            Separator {}

            // apps
            Row {
                id: apps
                height: parent.height
                spacing: 2
                Repeater {
                    model: dockWin.apps
                    delegate: Item {
                        id: tile
                        required property var modelData
                        required property int index
                        readonly property int distance: dockWin.hovered < 0 ? 99 : Math.abs(index - dockWin.hovered)
                        readonly property real grow: distance === 0 ? dockWin.zoom : distance === 1 ? 1 + (dockWin.zoom - 1) * 0.4 : 1
                        width: dockWin.iconSize * grow + 12
                        height: apps.height
                        z: dockWin.dragIndex === index ? 10 : 0
                        Behavior on width { NumberAnimation { duration: 180 * Theme.animationSpeed; easing.type: Easing.OutCubic } }

                        // while another pinned app is dragged past, make room
                        readonly property real shift: {
                            var d = dockWin.dragIndex, to = dockWin.dragTarget;
                            if (d < 0 || index === d) return 0;
                            if (index > d && index <= to) return -dockWin.slotWidth;
                            if (index < d && index >= to) return dockWin.slotWidth;
                            return 0;
                        }
                        transform: Translate {
                            x: dockWin.dragIndex === tile.index ? dockWin.dragOffset : tile.shift
                            Behavior on x { enabled: dockWin.dragIndex !== tile.index; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        }

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.verticalCenter: parent.verticalCenter
                            width: dockWin.iconSize + 8; height: width; radius: 14
                            color: Theme.c.onSurface
                            opacity: tile.modelData.active ? 0.1 : 0
                            Behavior on opacity { NumberAnimation { duration: 200 } }
                        }

                        Image {
                            id: icon
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: dockWin.iconSize; height: width
                            y: (parent.height - height) / 2 - (tile.grow - 1) * dockWin.iconSize * 0.55
                            source: tile.modelData.icon || ""
                            sourceSize: Qt.size(96, 96)
                            smooth: true
                            mipmap: true
                            asynchronous: true
                            scale: tile.grow * (tileMouse.pressed ? 0.9 : 1)
                            transformOrigin: Item.Bottom
                            // pulses while the app is starting up
                            opacity: tile.modelData.launching ? pulse.value : 1
                            QtObject {
                                id: pulse
                                property real value: 1
                                SequentialAnimation on value {
                                    running: !!tile.modelData.launching
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.4; duration: 450; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 1; duration: 450; easing.type: Easing.InOutSine }
                                }
                            }
                            Behavior on scale { NumberAnimation { duration: 180 * Theme.animationSpeed; easing.type: Easing.OutCubic } }
                            Behavior on y { NumberAnimation { duration: 180 * Theme.animationSpeed; easing.type: Easing.OutCubic } }

                            // unread badge
                            Rectangle {
                                readonly property int count: tile.modelData.badge || 0
                                visible: count !== 0
                                anchors { right: parent.right; top: parent.top; rightMargin: -5; topMargin: -4 }
                                height: count < 0 ? 10 : 18
                                width: count < 0 ? 10 : Math.max(18, badgeText.implicitWidth + 10)
                                radius: height / 2
                                color: Theme.c.error
                                border.width: 2
                                border.color: Theme.c.surfaceContainer
                                scale: 1 / Math.max(1, tile.grow)
                                transformOrigin: Item.TopRight
                                UText {
                                    id: badgeText
                                    visible: parent.count > 0
                                    anchors.centerIn: parent
                                    text: parent.count > 99 ? "99+" : parent.count
                                    size: 10.5
                                    weight: Font.Bold
                                    color: Theme.c.onError
                                }
                            }
                        }
                        // letter tile until the icon arrives
                        Rectangle {
                            visible: icon.status !== Image.Ready
                            anchors.fill: icon
                            radius: 12
                            color: Theme.c.secondaryContainer
                            scale: icon.scale
                            transformOrigin: Item.Bottom
                            UText { anchors.centerIn: parent; text: (tile.modelData.name || "?").charAt(0).toUpperCase(); size: 18; weight: Font.Bold; color: Theme.c.onSecondaryContainer }
                        }

                        // running indicator
                        Rectangle {
                            visible: tile.modelData.running
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: parent.height - 7
                            height: 4; radius: 2
                            width: tile.modelData.active ? 16 : 5
                            color: tile.modelData.active ? Theme.c.primary : Theme.c.onSurfaceVariant
                            Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                        }

                        // name label
                        Rectangle {
                            visible: opacity > 0
                            opacity: dockWin.hovered === tile.index && !dockWin.menuApp ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 140 } }
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: icon.y - dockWin.iconSize * (tile.grow - 1) - height - 10
                            height: 30; radius: 15
                            width: label.implicitWidth + 24
                            color: Theme.c.inverseSurface
                            UText { id: label; anchors.centerIn: parent; text: tile.modelData.name; size: 13; weight: Font.Medium; color: Theme.c.inverseOnSurface }
                        }

                        MouseArea {
                            id: tileMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                            cursorShape: Qt.PointingHandCursor
                            onContainsMouseChanged: {
                                if (containsMouse) dockWin.hovered = tile.index;
                                else if (dockWin.hovered === tile.index) dockWin.hovered = -1;
                            }
                            property real pressX: 0
                            property bool dragged: false
                            onPressed: (e) => { pressX = mapToItem(apps, e.x, 0).x; dragged = false; }
                            onPositionChanged: (e) => {
                                if (!(pressedButtons & Qt.LeftButton) || !tile.modelData.pinned) return;
                                var dx = mapToItem(apps, e.x, 0).x - pressX;
                                if (!dragged && Math.abs(dx) < 8) return;
                                dragged = true;
                                dockWin.hovered = -1;
                                dockWin.dragIndex = tile.index;
                                dockWin.dragOffset = dx;
                                dockWin.dragTarget = Math.max(0, Math.min(dockWin.pinnedCount - 1, tile.index + Math.round(dx / dockWin.slotWidth)));
                            }
                            onReleased: {
                                if (!dragged) return;
                                if (dockWin.dragTarget !== tile.index) Dock.movePinned(tile.modelData.key, dockWin.dragTarget);
                                dockWin.dragIndex = -1;
                                dockWin.dragTarget = -1;
                                dockWin.dragOffset = 0;
                            }
                            onClicked: (e) => {
                                if (dragged) return;
                                if (e.button === Qt.RightButton) {
                                    dockWin.playerOpen = false;
                                    dockWin.pickerKey = "";
                                    dockWin.menuApp = dockWin.menuApp && dockWin.menuApp.key === tile.modelData.key ? null : tile.modelData;
                                    dockWin.menuX = tile.mapToItem(null, tile.width / 2, 0).x;
                                    maskTimer.restart();
                                } else if (e.button === Qt.MiddleButton) {
                                    Dock.launch(tile.modelData.key);
                                } else if (tile.modelData.windows.length > 1) {
                                    dockWin.menuApp = null;
                                    dockWin.playerOpen = false;
                                    dockWin.pickerKey = dockWin.pickerKey === tile.modelData.key ? "" : tile.modelData.key;
                                    dockWin.pickerX = tile.mapToItem(null, tile.width / 2, 0).x;
                                    maskTimer.restart();
                                } else {
                                    dockWin.menuApp = null;
                                    dockWin.pickerKey = "";
                                    Dock.click(tile.modelData.key, dockWin.monitor);
                                }
                            }
                        }
                    }
                }
            }

            Separator {}

            // tray + quick icons
            DockButton {
                width: 32
                onClicked: Dock.openTray()
                MIcon { anchors.centerIn: parent; icon: Icons.expand_less; size: 22; color: Theme.c.onSurfaceVariant }
            }
            DockButton {
                visible: Dock.language !== ""
                width: langText.implicitWidth + 20
                onClicked: Dock.switchLanguage()
                UText { id: langText; anchors.centerIn: parent; text: Dock.language; size: 13; weight: Font.Medium; color: Theme.c.onSurfaceVariant }
            }
            Item {
                width: quick.width + 16
                height: parent.height
                Rectangle {
                    anchors.fill: parent; anchors.topMargin: 8; anchors.bottomMargin: 8
                    radius: height / 2
                    color: Theme.c.onSurface
                    opacity: quickMouse.containsMouse ? 0.08 : 0
                }
                Row {
                    id: quick
                    anchors.centerIn: parent
                    spacing: 10
                    MIcon { icon: Dock.network === "wifi" ? Icons.wifi : Dock.network === "off" ? Icons.wifi_off : Icons.lan; size: 20; color: Theme.c.onSurface }
                    MIcon { icon: Icons.volume_up; size: 20; color: Theme.c.onSurface }
                }
                MouseArea {
                    id: quickMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Dock.openQuickSettings()
                    onWheel: (w) => Dock.volume(w.angleDelta.y > 0 ? 1 : -1)
                }
            }
            // clock
            Item {
                width: clockCol.width + 24
                height: parent.height
                Rectangle {
                    anchors.fill: parent; anchors.topMargin: 6; anchors.bottomMargin: 6
                    radius: height / 2
                    color: Theme.c.primaryContainer
                }
                Column {
                    id: clockCol
                    anchors.centerIn: parent
                    UText {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: dockWin.cfg.clock_format === "24h"
                              ? Qt.formatTime(dockWin.now, dockWin.cfg.clock_seconds ? "HH:mm:ss" : "HH:mm")
                              : Qt.formatTime(dockWin.now, dockWin.cfg.clock_seconds ? "h:mm:ss AP" : "h:mm AP")
                        size: 14; weight: Font.DemiBold
                        color: Theme.c.onPrimaryContainer
                        font.features: { "tnum": 1 }
                    }
                    UText {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Qt.formatDate(dockWin.now, "ddd d MMM")
                        size: 11.5
                        color: Theme.c.onPrimaryContainer
                        opacity: 0.8
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Dock.openNotifications() }
            }
        }
    }

    component Separator: Rectangle {
        width: 1
        height: dockWin.iconSize * 0.6
        anchors.verticalCenter: parent ? parent.verticalCenter : undefined
        color: Theme.c.outlineVariant
    }

    component DockButton: Item {
        id: btn
        signal clicked()
        width: dockWin.iconSize + 12
        height: dockWin.pillHeight
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width, dockWin.iconSize + 8); height: dockWin.iconSize + 8
            radius: height / 2
            color: Theme.c.onSurface
            opacity: btnMouse.pressed ? 0.14 : btnMouse.containsMouse ? 0.08 : 0
        }
        MouseArea { id: btnMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: btn.clicked() }
    }

    // ---- window picker (apps with several windows) --------------------------------------
    Card {
        id: picker
        readonly property var app: dockWin.pickerApp
        readonly property var wins: app ? app.windows : []
        readonly property int columns: Math.min(4, Math.max(1, wins.length))
        readonly property real cardW: 236
        readonly property real cardH: 176
        visible: !!app && wins.length > 1
        tone: "surface"
        width: columns * cardW + (columns - 1) * 8 + 24
        height: pickerTitle.height + pickerGrid.height + 36
        x: Math.max(12, Math.min(dockWin.width - width - 12, dockWin.pickerX - width / 2))
        y: pill.y - height - 12
        HoverHandler { onHoveredChanged: hovered ? dockWin.keepPopups() : dockWin.releasePopups() }

        function placeThumbnails() {
            if (!visible) { Dock.clearThumbnails(dockWin); return; }
            var items = [];
            for (var i = 0; i < pickerRepeater.count; i++) {
                var card = pickerRepeater.itemAt(i);
                if (!card) continue;
                var p = card.preview.mapToItem(null, 0, 0);
                items.push({ hwnd: card.hwnd, x: p.x + 4, y: p.y + 4, w: card.preview.width - 8, h: card.preview.height - 8 });
            }
            Dock.showThumbnails(dockWin, items);
        }
        Timer { id: thumbTimer; interval: 40; onTriggered: picker.placeThumbnails() }
        onVisibleChanged: { maskTimer.restart(); thumbTimer.restart(); }
        onXChanged: thumbTimer.restart()
        onYChanged: thumbTimer.restart()
        onWinsChanged: thumbTimer.restart()

        UText {
            id: pickerTitle
            x: 16; y: 12
            text: picker.app ? picker.app.name + "  \u00b7  " + picker.wins.length + " windows" : ""
            size: 14.5; weight: Font.Medium
        }
        Grid {
            id: pickerGrid
            x: 12
            anchors.top: pickerTitle.bottom
            anchors.topMargin: 10
            columns: picker.columns
            spacing: 8
            Repeater {
                id: pickerRepeater
                model: picker.wins
                onItemAdded: thumbTimer.restart()
                delegate: Item {
                    id: winCard
                    required property var modelData
                    readonly property int hwnd: modelData.hwnd
                    property alias preview: previewBox
                    width: picker.cardW; height: picker.cardH

                    Rectangle {
                        anchors.fill: parent
                        radius: 20
                        color: winMouse.containsMouse ? Theme.c.secondaryContainer : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }
                    Rectangle {
                        id: previewBox
                        x: 8; y: 8
                        width: parent.width - 16
                        height: parent.height - 48
                        radius: 14
                        color: Theme.c.surfaceContainerHighest
                        MIcon {
                            anchors.centerIn: parent
                            visible: winCard.modelData.minimized
                            icon: Icons.expand_less
                            size: 28
                            color: Theme.c.onSurfaceVariant
                        }
                    }
                    UText {
                        anchors { left: parent.left; leftMargin: 14; right: closeWin.left; rightMargin: 6; bottom: parent.bottom; bottomMargin: 12 }
                        text: winCard.modelData.title
                        size: 13
                        color: winMouse.containsMouse ? Theme.c.onSecondaryContainer : Theme.c.onSurface
                    }
                    MouseArea {
                        id: winMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            Dock.focusWindow(winCard.hwnd);
                            dockWin.pickerKey = "";
                            Dock.clearThumbnails(dockWin);
                        }
                    }
                    IconButton {
                        id: closeWin
                        anchors { right: parent.right; rightMargin: 8; bottom: parent.bottom; bottomMargin: 6 }
                        visible: winMouse.containsMouse || hovered
                        property bool hovered: false
                        icon: Icons.close; size: 28; iconSize: 16
                        onClicked: Dock.closeWindow(winCard.hwnd)
                    }
                }
            }
        }
    }
    Connections {
        target: picker
        function onVisibleChanged() { if (!picker.visible) Dock.clearThumbnails(dockWin); }
    }

    // ---- app menu --------------------------------------------------------------------
    Card {
        id: menu
        visible: dockWin.menuApp !== null
        onVisibleChanged: maskTimer.restart()
        tone: "surface"
        width: 280
        height: menuCol.implicitHeight + 16
        x: Math.max(12, Math.min(dockWin.width - width - 12, dockWin.menuX - width / 2))
        y: pill.y - height - 12
        opacity: visible ? 1 : 0
        HoverHandler { onHoveredChanged: hovered ? dockWin.keepPopups() : dockWin.releasePopups() }

        Column {
            id: menuCol
            x: 8; y: 8
            width: parent.width - 16
            spacing: 2

            UText {
                width: parent.width
                leftPadding: 12; topPadding: 6; bottomPadding: 6
                text: dockWin.menuApp ? dockWin.menuApp.name : ""
                size: 15; weight: Font.Medium
            }
            Repeater {
                model: dockWin.menuApp ? dockWin.menuApp.windows : []
                MenuRow {
                    required property var modelData
                    icon: Icons.open_in_new
                    text: modelData.title
                    onClicked: { Dock.focusWindow(modelData.hwnd); dockWin.menuApp = null; }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.c.outlineVariant; visible: dockWin.menuApp && dockWin.menuApp.windows.length > 0 }

            // What the app itself offers: its tasks, and the things it opened
            // lately. Fetched when the menu opens, because reading it touches
            // the shell and a few files on disk.
            Repeater {
                model: dockWin.jumpRows
                MenuRow {
                    required property var modelData
                    icon: modelData.kind === "task" ? Icons.add : Icons.schedule
                    text: modelData.title
                    subtext: modelData.subtitle
                    onClicked: { Dock.openJumpItem(modelData.target, modelData.args); dockWin.menuApp = null; }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.c.outlineVariant; visible: dockWin.jumpRows.length > 0 }
            MenuRow {
                icon: Icons.add
                text: dockWin.menuApp && dockWin.menuApp.running ? "New window" : "Open"
                onClicked: { Dock.launch(dockWin.menuApp.key); dockWin.menuApp = null; }
            }
            MenuRow {
                icon: Icons.push_pin
                text: dockWin.menuApp && dockWin.menuApp.pinned ? "Unpin from dock" : "Pin to dock"
                onClicked: { Dock.setPinned(dockWin.menuApp.key, !dockWin.menuApp.pinned); dockWin.menuApp = null; }
            }
            MenuRow {
                visible: dockWin.menuApp && dockWin.menuApp.running
                icon: Icons.close
                text: dockWin.menuApp && dockWin.menuApp.windows.length > 1 ? "Close all windows" : "Close window"
                danger: true
                onClicked: { Dock.closeApp(dockWin.menuApp.key, dockWin.monitor); dockWin.menuApp = null; }
            }
        }
    }

    component MenuRow: Item {
        id: mrow
        property string icon: ""
        property string text: ""
        property string subtext: ""
        property bool danger: false
        signal clicked()
        readonly property bool twoLine: subtext !== ""
        width: parent ? parent.width : 200
        height: visible ? (twoLine ? 48 : 40) : 0
        Rectangle { anchors.fill: parent; radius: 12; color: Theme.c.onSurface; opacity: mrowMouse.containsMouse ? 0.08 : 0 }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 12; spacing: 12
            MIcon { icon: mrow.icon; size: 18; color: mrow.danger ? Theme.c.error : Theme.c.onSurfaceVariant; anchors.verticalCenter: parent.verticalCenter }
            Column {
                width: mrow.width - 56
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                UText { width: parent.width; text: mrow.text; size: 13.5; elide: Text.ElideRight; color: mrow.danger ? Theme.c.error : Theme.c.onSurface }
                UText {
                    width: parent.width
                    visible: mrow.twoLine
                    text: mrow.subtext
                    size: 11.5
                    elide: Text.ElideMiddle
                    color: Theme.c.onSurfaceVariant
                }
            }
        }
        MouseArea { id: mrowMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: mrow.clicked() }
    }

    // ---- search ----------------------------------------------------------------------
    SearchPanel {
        id: search
        visible: dockWin.searchHere
        onVisibleChanged: maskTimer.restart()
        onHeightChanged: maskTimer.restart()
        x: Math.round((dockWin.width - width) / 2)
        y: pill.y - height - 14
        opacity: visible ? 1 : 0
        scale: visible ? 1 : 0.97
        transformOrigin: Item.Bottom
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    // Losing focus (clicking elsewhere) closes search; ignore the moment of opening.
    property bool searchArmed: false
    Timer { id: armTimer; interval: 350; onTriggered: dockWin.searchArmed = true }
    Connections {
        target: Search
        function onOpenChanged() {
            if (dockWin.searchHere) {
                dockWin.menuApp = null;
                dockWin.playerOpen = false;
                dockWin.searchArmed = false;
                Dock.setActivatable(dockWin, true);
                // Shown first (it may have been idle behind a fullscreen app), then focused.
                Qt.callLater(function () { Search.focusWindow(dockWin); search.focusInput(); });
                armTimer.restart();
            } else {
                Dock.setActivatable(dockWin, false);
            }
            maskTimer.restart();
        }
    }
    onActiveChanged: if (!active && searchHere && searchArmed) Search.setOpen(false)

    // ---- player popup ------------------------------------------------------------------
    Item {
        id: player
        visible: dockWin.playerOpen && !!Media.playing
        onVisibleChanged: maskTimer.restart()
        width: 400
        height: playerLoader.item ? playerLoader.item.height : 0
        onHeightChanged: maskTimer.restart()
        x: Math.max(12, pill.x + nowPlaying.x + 10)
        y: pill.y - height - 12
        HoverHandler { onHoveredChanged: hovered ? dockWin.keepPopups() : dockWin.releasePopups() }
        Loader {
            id: playerLoader
            active: player.visible
            source: "widgets/MediaWidget.qml"
            onLoaded: item.options = { style: "card", width: 400, lyrics: true, lyric_lines: 5 }
        }
    }
}
