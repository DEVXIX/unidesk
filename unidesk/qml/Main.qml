import QtQuick
import QtQuick.Window
import "components"
import "Icons.js" as Icons
import "Schema.js" as Schema

// One desk per screen: a transparent window over that screen's usable area,
// clipped (for drawing and for clicks) to where its widgets are, so the
// desktop underneath stays clickable. One window per screen = one GPU context
// each, which keeps memory low. Widgets are matched by id, so saving
// config.yaml updates them in place; each shows on the screen its `screen`
// names (1 = the main display).
Window {
    id: desk
    required property QtObject slot
    readonly property int number: slot.number

    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
    color: "transparent"
    title: "unidesk"
    screen: {
        var all = Qt.application.screens;
        for (var i = 0; i < all.length; i++) if (all[i].name === slot.name) return all[i];
        return all[0];
    }
    x: slot.area.x
    y: slot.area.y
    width: slot.area.width
    height: slot.area.height
    // Shown only once it is pinned to the desktop and clipped, so it never
    // flashes over other windows; hidden while a fullscreen app covers the screen.
    property bool ready: false
    visible: ready && (!slot.suspended || Desk.editing)

    property var frames: ({})
    property bool addOpen: false
    property bool settingsOpen: false
    readonly property int shadowPad: 24

    function sync() {
        var seen = {}, list = Desk.widgets;
        for (var i = 0; i < list.length; i++) {
            var spec = list[i];
            if (spec.display !== desk.number) continue;
            seen[spec.id] = true;
            var f = frames[spec.id];
            if (f && f.spec.type !== spec.type) { f.destroy(); f = null; }
            if (f) {
                if (!f.dragging && !f.resizing) f.spec = spec;
            } else {
                f = frameComponent.createObject(layer, { spec: spec, slot: desk.slot });
                f.geometryMoved.connect(maskTimer.restart);
                frames[spec.id] = f;
            }
        }
        for (var id in frames) {
            if (!seen[id]) {
                frames[id].destroy();
                delete frames[id];
            }
        }
        refreshSelection();
        maskTimer.restart();
    }

    function refreshSelection() {
        for (var id in frames) frames[id].selected = id === Desk.selected;
        var f = frames[Desk.selected] || null;
        panel.target = f;
        if (f) { addOpen = false; settingsOpen = false; }
    }
    function deselect() {
        Desk.select("");
        addOpen = false;
        settingsOpen = false;
    }

    // Clip the window to the widgets (plus room for shadows and the banner).
    function updateMask() {
        var rects = [];
        if (Desk.editing) {
            rects.push([0, 0, width, height]);
        } else {
            for (var id in frames) {
                var f = frames[id];
                rects.push([f.x - shadowPad, f.y - shadowPad, f.width + shadowPad * 2, f.height + shadowPad * 2]);
            }
            if (banner.visible) rects.push([banner.x, banner.y, banner.width, banner.height]);
        }
        Desk.setMask(desk, rects);
    }

    Timer { id: maskTimer; interval: 60; onTriggered: desk.updateMask() }
    Connections {
        target: Desk
        function onWidgetsChanged() { desk.sync(); }
        function onSelectedChanged() { desk.refreshSelection(); }
        function onEditingChanged() {
            if (!Desk.editing) { desk.addOpen = false; desk.settingsOpen = false; }
            desk.updateMask();
        }
        function onErrorChanged() { maskTimer.restart(); }
    }
    onWidthChanged: maskTimer.restart()
    onHeightChanged: maskTimer.restart()
    onNumberChanged: sync()
    onVisibleChanged: if (visible) { Desk.registerWindow(desk); maskTimer.restart(); }
    Component.onCompleted: {
        sync();
        Desk.registerWindow(desk);
        updateMask();
        ready = true;
    }

    Component { id: frameComponent; WidgetFrame {} }

    // Dim the desktop while editing; clicking empty space deselects.
    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: Desk.editing ? 0.25 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        MouseArea { anchors.fill: parent; enabled: Desk.editing; onClicked: desk.deselect() }
    }

    // Sized from the window directly (not anchors), so widgets are placed
    // correctly before the window is first shown.
    Item { id: layer; width: desk.width; height: desk.height }

    // Options for the selected widget, beside it.
    CustomizePanel {
        id: panel
        z: 50
        x: !target ? 0 : (target.x + target.width + 24 + width < desk.width ? target.x + target.width + 24 : Math.max(12, target.x - width - 24))
        y: !target ? 0 : Math.max(76, Math.min(desk.height - height - 12, target.y))
        onClose: Desk.select("")
    }

    // Top centre: edit banner (with Add widget / Done), or a config error.
    Rectangle {
        id: banner
        visible: Desk.editing || Desk.error !== ""
        onVisibleChanged: maskTimer.restart()
        anchors.horizontalCenter: parent.horizontalCenter
        y: 16
        z: 100
        height: 52
        width: row.implicitWidth + 16
        radius: 26
        color: Desk.error ? Theme.c.errorContainer : Theme.c.inverseSurface

        Row {
            id: row
            anchors.centerIn: parent
            spacing: 10
            MIcon {
                anchors.verticalCenter: parent.verticalCenter
                leftPadding: 10
                icon: Desk.error ? Icons.close : Icons.widgets
                size: 20
                color: Desk.error ? Theme.c.onErrorContainer : Theme.c.inverseOnSurface
            }
            UText {
                anchors.verticalCenter: parent.verticalCenter
                text: Desk.error ? Desk.error
                    : Desk.screenCount > 1 ? "Screen " + desk.number + "  ·  drag to move, even to another screen  ·  corner to resize"
                    : "Drag to move  ·  corner to resize  ·  click to customize"
                size: 14
                elide: Text.ElideNone
                color: Desk.error ? Theme.c.onErrorContainer : Theme.c.inverseOnSurface
            }
            Rectangle {
                visible: Desk.editing
                anchors.verticalCenter: parent.verticalCenter
                width: addRow.implicitWidth + 26; height: 38; radius: 19
                color: desk.addOpen ? Theme.c.primary : "transparent"
                border.width: desk.addOpen ? 0 : 1.5
                border.color: Theme.c.inverseOnSurface
                Row {
                    id: addRow
                    anchors.centerIn: parent
                    spacing: 4
                    MIcon { icon: Icons.add; size: 18; color: desk.addOpen ? Theme.c.onPrimary : Theme.c.inverseOnSurface; anchors.verticalCenter: parent.verticalCenter }
                    UText { text: "Add widget"; size: 14; weight: Font.Medium; color: desk.addOpen ? Theme.c.onPrimary : Theme.c.inverseOnSurface; anchors.verticalCenter: parent.verticalCenter }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { var open = !desk.addOpen; Desk.select(""); desk.settingsOpen = false; desk.addOpen = open; } }
            }
            IconButton {
                visible: Desk.editing
                anchors.verticalCenter: parent.verticalCenter
                icon: Icons.settings; size: 38; iconSize: 20
                color: desk.settingsOpen ? Theme.c.primary : "transparent"
                iconColor: desk.settingsOpen ? Theme.c.onPrimary : Theme.c.inverseOnSurface
                onClicked: { var open = !desk.settingsOpen; Desk.select(""); desk.addOpen = false; desk.settingsOpen = open; }
            }
            Rectangle {
                visible: Desk.editing
                anchors.verticalCenter: parent.verticalCenter
                width: doneText.implicitWidth + 32; height: 38; radius: 19
                color: Theme.c.inversePrimary
                UText { id: doneText; anchors.centerIn: parent; text: "Done"; size: 14; weight: Font.Medium; color: Theme.c.onPrimaryContainer }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Desk.setEditing(false) }
            }
        }
    }

    SettingsPanel {
        z: 100
        visible: Desk.editing && desk.settingsOpen
        x: banner.x + banner.width - width
        y: banner.y + banner.height + 8
        onClose: desk.settingsOpen = false
    }

    // Add widget menu
    Card {
        id: addMenu
        z: 100
        visible: Desk.editing && desk.addOpen
        tone: "surface"
        width: 260
        height: Math.min(desk.height - y - 12, addColumn.implicitHeight + 16)
        x: banner.x + banner.width - width - 8
        y: banner.y + banner.height + 8
        clip: true
        Flickable {
            anchors.fill: parent
            anchors.margins: 8
            contentHeight: addColumn.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: addColumn
                width: parent.width
                Repeater {
                    model: Schema.types
                    Item {
                        required property var modelData
                        width: addColumn.width; height: 44
                        Rectangle { anchors.fill: parent; radius: 14; color: Theme.c.onSurface; opacity: itemMouse.containsMouse ? 0.08 : 0 }
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 12; spacing: 12
                            MIcon { icon: Icons[modelData.icon]; size: 20; color: Theme.c.primary; anchors.verticalCenter: parent.verticalCenter }
                            UText { text: modelData.label; size: 14.5; anchors.verticalCenter: parent.verticalCenter }
                        }
                        MouseArea {
                            id: itemMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                desk.addOpen = false;
                                Desk.select(Desk.addWidget(modelData.type, desk.number));
                            }
                        }
                    }
                }
            }
        }
    }
}
