import QtQuick
import "../components"
import "../Icons.js" as Icons

// Code activity from Gitea, GitHub or both: contribution graph tinted with
// the theme, a few stats, recent activity marked with where it happened.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property var d: GitHub.data
    readonly property int activityRows: opt("activity", 3)

    function ago(iso) {
        var s = (Date.now() - new Date(iso).getTime()) / 1000;
        if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m";
        if (s < 86400) return Math.round(s / 3600) + "h";
        return Math.round(s / 86400) + "d";
    }

    implicitWidth: opt("width", 430)
    implicitHeight: d ? column.implicitHeight + 28 : 90

    UText {
        visible: !root.d
        anchors.centerIn: parent
        width: parent.width - 32
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: GitHub.error !== "" ? GitHub.error : "Loading code activity…"
        color: GitHub.error !== "" ? Theme.c.error : Theme.c.onSurfaceVariant
    }

    Column {
        id: column
        visible: !!root.d
        x: 14; y: 14
        width: parent.width - 28
        spacing: 12

        // header
        Item {
            width: parent.width; height: 46
            ShapedImage { id: av; width: 46; height: 46; shape: "cookie12"; source: root.d ? root.d.avatar : "" }
            Column {
                anchors { left: av.right; leftMargin: 12; right: chips.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
                UText { width: parent.width; text: root.d ? root.d.name : ""; size: 17; weight: Font.Medium }
                UText {
                    width: parent.width
                    text: root.d ? root.d.accounts.map(function (a) { return "@" + a.login + (root.d.accounts.length > 1 ? " · " + a.source : ""); }).join("   ") : ""
                    size: 12.5; color: Theme.c.onSurfaceVariant
                }
            }
            Row {
                id: chips
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 6
                Repeater {
                    model: root.d ? [
                        [Icons.star, root.d.stars],
                        [Icons.book_2, root.d.repos],
                        [Icons.local_fire_department, root.d.streak]
                    ].concat(root.d.notifications !== null && root.d.notifications !== undefined ? [[Icons.notifications, root.d.notifications]] : []) : []
                    Rectangle {
                        required property var modelData
                        height: 28; radius: 14
                        width: chip.implicitWidth + 18
                        color: Theme.c.secondaryContainer
                        Row {
                            id: chip
                            anchors.centerIn: parent
                            spacing: 3
                            MIcon { icon: modelData[0]; size: 15; fill: 1; color: Theme.c.onSecondaryContainer; anchors.verticalCenter: parent.verticalCenter }
                            UText { text: modelData[1]; size: 12.5; weight: Font.Medium; color: Theme.c.onSecondaryContainer; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
            MouseArea {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                width: parent.width * 0.5
                cursorShape: Qt.PointingHandCursor
                onClicked: Desk.openUrl(root.d.url)
            }
        }

        // contribution graph
        Row {
            id: graph
            readonly property int weeks: root.d ? root.d.weeks.length : 1
            readonly property real gap: 3
            readonly property real cell: Math.floor((column.width - gap * (weeks - 1)) / weeks)
            spacing: gap
            Repeater {
                model: root.d ? root.d.weeks : []
                Column {
                    required property var modelData
                    spacing: graph.gap
                    Repeater {
                        model: modelData
                        Rectangle {
                            required property int modelData
                            width: graph.cell; height: graph.cell
                            radius: graph.cell * 0.3
                            color: modelData < 0 ? "transparent"
                                 : modelData === 0 ? Theme.c.surfaceContainerHighest
                                 : Qt.alpha(Theme.c.primary, [0, 0.35, 0.6, 0.82, 1][modelData])
                        }
                    }
                }
            }
        }

        UText {
            text: root.d ? root.d.contributions + " contributions in the last year" + (root.d.streak > 1 ? " · " + root.d.streak + " day streak" : "") : ""
            size: 12.5
            color: Theme.c.onSurfaceVariant
        }

        // activity
        Column {
            width: parent.width
            spacing: 4
            Repeater {
                model: root.d ? root.d.activity.slice(0, root.activityRows) : []
                Item {
                    required property var modelData
                    width: column.width; height: 34
                    Rectangle {
                        anchors.fill: parent; radius: 12
                        color: Theme.c.onSurface
                        opacity: rowMouse.containsMouse ? 0.06 : 0
                    }
                    Rectangle {
                        id: iconBg
                        x: 4; anchors.verticalCenter: parent.verticalCenter
                        width: 28; height: 28; radius: 14
                        color: Theme.c.surfaceContainerHighest
                        MIcon { anchors.centerIn: parent; icon: Icons[modelData.icon] || Icons.commit; size: 16; color: Theme.c.primary }
                    }
                    Rectangle {
                        id: sourceChip
                        visible: root.d && root.d.sources.length > 1
                        anchors { right: when.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        width: visible ? sourceText.implicitWidth + 12 : 0; height: 20; radius: 10
                        color: modelData.source === "gitea" ? Theme.c.tertiaryContainer : Theme.c.secondaryContainer
                        UText {
                            id: sourceText
                            anchors.centerIn: parent
                            text: modelData.source
                            size: 11
                            color: modelData.source === "gitea" ? Theme.c.onTertiaryContainer : Theme.c.onSecondaryContainer
                        }
                    }
                    UText {
                        anchors { left: iconBg.right; leftMargin: 10; right: sourceChip.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        textFormat: Text.StyledText
                        text: modelData.text + " <b>" + modelData.repo + "</b>"
                        size: 13.5
                    }
                    UText {
                        id: when
                        anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                        text: root.ago(modelData.at)
                        size: 12; color: Theme.c.onSurfaceVariant
                    }
                    MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Desk.openUrl(modelData.url) }
                }
            }
        }
    }
}
