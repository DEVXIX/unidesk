import QtQuick
import "components"
import "Icons.js" as Icons
import "Schema.js" as Schema

// Options for one widget, next to it on the desk. Every change is written
// to config.yaml straight away and the widget updates live.
Card {
    id: panel
    property Item target: null   // the selected WidgetFrame
    readonly property var spec: target ? target.spec : null
    property bool confirmRemove: false
    signal close()

    tone: "surface"
    width: 320
    height: Math.min(parent ? parent.height - 40 : 700, body.implicitHeight + 32)
    visible: spec !== null
    onTargetChanged: confirmRemove = false

    // Clicks inside the panel stay inside it.
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: (w) => w.accepted = true }

    Flickable {
        anchors.fill: parent
        anchors.margins: 16
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            width: parent.width
            spacing: 14

            Item {
                width: parent.width; height: 40
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    UText { text: panel.spec ? Schema.labelFor(panel.spec.type) : ""; size: 19; weight: Font.Medium }
                    UText { text: panel.spec ? panel.spec.id : ""; size: 12.5; color: Theme.c.onSurfaceVariant }
                }
                IconButton {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    icon: Icons.close; size: 36
                    onClicked: panel.close()
                }
            }

            OptionRow {
                field: ({ key: "scale", label: "Size", kind: "slider", min: 0.4, max: 2.5, step: 0.05, def: 1 })
                value: panel.spec ? panel.spec.scale : 1
                onChanged: (v) => Desk.setOption(panel.spec.id, "scale", v)
            }

            OptionRow {
                visible: Desk.screenCount > 1
                field: ({
                    key: "screen", label: "Screen", kind: "choice", def: "1",
                    options: Array.from({ length: Desk.screenCount }, (_, i) => String(i + 1))
                })
                value: panel.spec ? String(panel.spec.display || 1) : "1"
                onChanged: (v) => Desk.setOption(panel.spec.id, "screen", Number(v))
            }

            // Kept to one virtual desktop. Only worth offering when there
            // is more than one to choose between.
            OptionRow {
                visible: Desktops.available && Desktops.count > 1
                field: ({
                    key: "desktop", label: "Desktop", kind: "choice", def: "all",
                    options: ["all"].concat(Array.from({ length: Desktops.count }, (_, i) => String(i + 1)))
                })
                value: panel.spec && panel.spec.options ? (panel.spec.options.desktop || "all") : "all"
                onChanged: (v) => Desk.setOption(panel.spec.id, "desktop", v)
            }

            // Which corner, edge or the centre the widget keeps its distance
            // from when the screen size changes. Changing it doesn't move it.
            OptionRow {
                field: ({ key: "anchor", label: "Sticks to", kind: "anchor", def: "top-left" })
                value: panel.spec ? panel.spec.anchor : "top-left"
                onChanged: (v) => { if (panel.target) panel.target.save({ anchor: v }); }
            }

            Repeater {
                model: panel.spec ? (Schema.fields[panel.spec.type] || []) : []
                OptionRow {
                    required property var modelData
                    field: modelData
                    value: panel.spec && panel.spec.options ? panel.spec.options[modelData.key] : undefined
                    onChanged: (v) => Desk.setOption(panel.spec.id, modelData.key, v)
                }
            }

            Rectangle { width: parent.width; height: 1; color: Theme.c.outlineVariant }

            Rectangle {
                width: parent.width; height: 44; radius: 22
                color: panel.confirmRemove ? Theme.c.error : Theme.c.errorContainer
                Behavior on color { ColorAnimation { duration: 150 } }
                Row {
                    anchors.centerIn: parent
                    spacing: 8
                    MIcon { icon: Icons.delete_; size: 20; color: panel.confirmRemove ? Theme.c.onError : Theme.c.onErrorContainer; anchors.verticalCenter: parent.verticalCenter }
                    UText {
                        text: panel.confirmRemove ? "Click again to remove" : "Remove widget"
                        size: 14.5; weight: Font.Medium
                        color: panel.confirmRemove ? Theme.c.onError : Theme.c.onErrorContainer
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (!panel.confirmRemove) { panel.confirmRemove = true; return; }
                        var id = panel.spec.id;
                        panel.close();
                        Desk.removeWidget(id);
                    }
                }
            }
        }
    }
}
