import QtQuick
import QtQuick.Window
import "components"
import "Icons.js" as Icons
import "Schema.js" as Schema

// The whole desk is one transparent window over the usable screen area,
// clipped (for drawing and for clicks) to where the widgets are, so the
// desktop underneath stays clickable. One window = one GPU context, which
// keeps memory low. Widgets are matched by id, so saving config.yaml
// updates them in place.
Window {
    id: desk
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
    color: "transparent"
    title: "unidesk"
    x: Desk.area.x
    y: Desk.area.y
    width: Desk.area.width
    height: Desk.area.height
    visible: !Desk.suspended

    property var frames: ({})
    property string selectedId: ""
    property bool addOpen: false
    property bool settingsOpen: false
    readonly property int shadowPad: 24

    function sync() {
        var seen = {}, list = Desk.widgets;
        for (var i = 0; i < list.length; i++) {
            var spec = list[i];
            seen[spec.id] = true;
            var f = frames[spec.id];
            if (f && f.spec.type !== spec.type) { f.destroy(); f = null; }
            if (f) {
                if (!f.dragging && !f.resizing) f.spec = spec;
            } else {
                f = frameComponent.createObject(layer, { spec: spec });
                f.geometryMoved.connect(maskTimer.restart);
                f.customize.connect(function (id) { return function () { desk.select(id); }; }(spec.id));
                frames[spec.id] = f;
            }
        }
        for (var id in frames) {
            if (!seen[id]) {
                frames[id].destroy();
                delete frames[id];
                if (selectedId === id) selectedId = "";
            }
        }
        refreshSelection();
        maskTimer.restart();
    }

    function select(id) {
        selectedId = selectedId === id ? "" : id;
        addOpen = false;
        settingsOpen = false;
        refreshSelection();
    }
    function refreshSelection() {
        for (var id in frames) frames[id].selected = id === selectedId;
        var f = frames[selectedId];
        panel.spec = f ? f.spec : null;
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
        function onEditingChanged() {
            if (!Desk.editing) { desk.selectedId = ""; desk.addOpen = false; desk.settingsOpen = false; desk.refreshSelection(); }
            desk.updateMask();
        }
        function onErrorChanged() { maskTimer.restart(); }
    }
    onWidthChanged: maskTimer.restart()
    onHeightChanged: maskTimer.restart()
    onVisibleChanged: if (visible) { Desk.registerWindow(desk); maskTimer.restart(); }
    Component.onCompleted: {
        sync();
        if (visible) Desk.registerWindow(desk);
    }

    Component { id: frameComponent; WidgetFrame {} }

    // Dim the desktop while editing; clicking empty space deselects.
    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: Desk.editing ? 0.25 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        MouseArea { anchors.fill: parent; enabled: Desk.editing; onClicked: { desk.selectedId = ""; desk.addOpen = false; desk.settingsOpen = false; desk.refreshSelection(); } }
    }

    Item { id: layer; anchors.fill: parent }

    // Options for the selected widget, beside it.
    CustomizePanel {
        id: panel
        z: 50
        readonly property var target: desk.frames[desk.selectedId] || null
        x: !target ? 0 : (target.x + target.width + 24 + width < desk.width ? target.x + target.width + 24 : Math.max(12, target.x - width - 24))
        y: !target ? 0 : Math.max(76, Math.min(desk.height - height - 12, target.y))
        onClose: desk.select(desk.selectedId)
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
                text: Desk.error ? Desk.error : "Drag to move  ·  corner to resize  ·  click to customize"
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
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { desk.addOpen = !desk.addOpen; desk.settingsOpen = false; desk.selectedId = ""; desk.refreshSelection(); } }
            }
            IconButton {
                visible: Desk.editing
                anchors.verticalCenter: parent.verticalCenter
                icon: Icons.settings; size: 38; iconSize: 20
                color: desk.settingsOpen ? Theme.c.primary : "transparent"
                iconColor: desk.settingsOpen ? Theme.c.onPrimary : Theme.c.inverseOnSurface
                onClicked: { desk.settingsOpen = !desk.settingsOpen; desk.addOpen = false; desk.selectedId = ""; desk.refreshSelection(); }
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
        height: addColumn.implicitHeight + 16
        x: banner.x + banner.width - width - 8
        y: banner.y + banner.height + 8
        Column {
            id: addColumn
            x: 8; y: 8
            width: parent.width - 16
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
                            var id = Desk.addWidget(modelData.type, Math.round(desk.width / 2 - 150), Math.round(desk.height / 2 - 100));
                            desk.selectedId = id;
                            Qt.callLater(desk.refreshSelection);
                        }
                    }
                }
            }
        }
    }
}
