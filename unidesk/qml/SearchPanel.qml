import QtQuick
import QtQuick.Effects
import "components"
import "Icons.js" as Icons

// Search: type to find apps, do maths, open a settings page, or hand off to
// file / web search. Up/Down to move, Enter to open, Esc to close.
Item {
    id: panel
    property int current: 0
    readonly property var results: Search.results
    signal closed()

    width: 640
    height: Math.min(520, box.height + list.contentHeight + 40)
    Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    function openSelected() {
        if (Search.activate(current)) Search.setOpen(false);
    }
    function focusInput() { input.forceActiveFocus(); input.selectAll(); }

    onResultsChanged: current = 0

    RectangularShadow {
        anchors.fill: bg
        radius: bg.radius
        blur: 32; spread: -2; offset.y: 8
        color: Qt.rgba(0, 0, 0, 0.45)
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

    // search box
    Rectangle {
        id: box
        x: 14; y: 14
        width: parent.width - 28
        height: 58
        radius: 29
        color: Theme.c.surfaceContainerHighest

        MIcon {
            id: glass
            x: 20
            anchors.verticalCenter: parent.verticalCenter
            icon: Icons.search
            size: 24
            color: Theme.c.primary
        }
        TextInput {
            id: input
            anchors { left: glass.right; leftMargin: 14; right: parent.right; rightMargin: 20; verticalCenter: parent.verticalCenter }
            font.family: Theme.font
            font.pixelSize: 19
            color: Theme.c.onSurface
            selectionColor: Theme.c.primary
            selectedTextColor: Theme.c.onPrimary
            clip: true
            onTextChanged: Search.setQuery(text)
            Keys.onPressed: (e) => {
                if (e.key === Qt.Key_Down) { panel.current = Math.min(panel.results.length - 1, panel.current + 1); list.positionViewAtIndex(panel.current, ListView.Contain); e.accepted = true; }
                else if (e.key === Qt.Key_Up) { panel.current = Math.max(0, panel.current - 1); list.positionViewAtIndex(panel.current, ListView.Contain); e.accepted = true; }
                else if (e.key === Qt.Key_Return || e.key === Qt.Key_Enter) { panel.openSelected(); e.accepted = true; }
                else if (e.key === Qt.Key_Escape) { Search.setOpen(false); e.accepted = true; }
            }
            UText {
                visible: input.text === ""
                anchors.verticalCenter: parent.verticalCenter
                text: Search.indexing ? "Finding your apps…" : "Search apps, settings, the web, or do maths"
                size: 17
                color: Theme.c.onSurfaceVariant
            }
        }
    }

    ListView {
        id: list
        anchors { left: parent.left; right: parent.right; top: box.bottom; bottom: parent.bottom; margins: 14; topMargin: 10 }
        clip: true
        model: panel.results
        spacing: 2
        boundsBehavior: Flickable.StopAtBounds
        section.property: "section"
        section.delegate: UText {
            required property string section
            width: list.width
            leftPadding: 14; topPadding: 10; bottomPadding: 4
            text: section
            size: 12.5; weight: Font.DemiBold
            color: Theme.c.primary
        }

        delegate: Item {
            id: row
            required property var modelData
            required property int index
            readonly property bool selected: panel.current === index
            width: list.width
            height: 54

            Rectangle {
                anchors.fill: parent
                radius: 18
                color: row.selected ? Theme.c.secondaryContainer : Theme.c.onSurface
                opacity: row.selected ? 1 : rowMouse.containsMouse ? 0.06 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }

            Item {
                id: iconBox
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                width: 34; height: 34
                Image {
                    anchors.fill: parent
                    visible: row.modelData.icon !== ""
                    source: row.modelData.icon
                    sourceSize: Qt.size(68, 68)
                    smooth: true; mipmap: true
                    asynchronous: true
                }
                MShape {
                    anchors.fill: parent
                    visible: row.modelData.icon === ""
                    shape: "cookie12"
                    color: row.selected ? Theme.c.primary : Theme.c.primaryContainer
                }
                MIcon {
                    anchors.centerIn: parent
                    visible: row.modelData.icon === ""
                    icon: Icons[row.modelData.glyph || "search"] || Icons.search
                    size: 18
                    fill: 1
                    color: row.selected ? Theme.c.onPrimary : Theme.c.onPrimaryContainer
                }
            }
            Column {
                anchors { left: iconBox.right; leftMargin: 14; right: enterHint.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
                UText {
                    width: parent.width
                    text: row.modelData.title
                    size: row.modelData.kind === "calc" ? 20 : 15.5
                    weight: row.modelData.kind === "calc" ? Font.DemiBold : Font.Medium
                    color: row.selected ? Theme.c.onSecondaryContainer : Theme.c.onSurface
                }
                UText {
                    width: parent.width
                    text: row.modelData.subtitle
                    size: 12
                    color: row.selected ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant
                    opacity: 0.85
                }
            }
            UText {
                id: enterHint
                anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                text: row.modelData.kind === "calc" ? "copy ↵" : "open ↵"
                size: 12
                color: Theme.c.onSecondaryContainer
                opacity: row.selected ? 0.8 : 0
            }
            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: panel.current = row.index
                onClicked: panel.openSelected()
            }
        }
    }
}
