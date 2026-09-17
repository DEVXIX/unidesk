import QtQuick
import "../components"
import "../Icons.js" as Icons

// Pull requests, issues and CI runs from GitHub and Gitea.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    property string tab: "pr"
    readonly property var list: tab === "ci" ? DevDash.runs : DevDash.items.filter(function (i) { return i.kind === root.tab; })
    readonly property int rows: opt("rows", 5)

    function ago(iso) {
        if (!iso) return "";
        var s = (Date.now() - new Date(iso).getTime()) / 1000;
        if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m";
        if (s < 86400) return Math.round(s / 3600) + "h";
        return Math.round(s / 86400) + "d";
    }
    function runIcon(status) {
        if (status === "success") return [Icons.task_alt, Theme.c.primary];
        if (status === "failure" || status === "cancelled" || status === "timed_out") return [Icons.error, Theme.c.error];
        return [Icons.pending, Theme.c.tertiary];
    }

    implicitWidth: opt("width", 420)
    implicitHeight: column.implicitHeight + 28

    Column {
        id: column
        x: 14; y: 14
        width: parent.width - 28
        spacing: 8

        Item {
            width: parent.width; height: 34
            UText { anchors.verticalCenter: parent.verticalCenter; text: "Code reviews"; size: 17; weight: Font.Medium }
            Row {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 6
                Repeater {
                    model: [["pr", "PRs"], ["issue", "Issues"], ["ci", "CI"]]
                    Rectangle {
                        required property var modelData
                        readonly property bool on: root.tab === modelData[0]
                        readonly property int count: modelData[0] === "ci" ? DevDash.runs.length : DevDash.items.filter(function (i) { return i.kind === modelData[0]; }).length
                        height: 30; radius: 15
                        width: tabText.implicitWidth + 22
                        color: on ? Theme.c.secondaryContainer : "transparent"
                        border.width: on ? 0 : 1
                        border.color: Theme.c.outlineVariant
                        UText { id: tabText; anchors.centerIn: parent; text: modelData[1] + (count ? " " + count : ""); size: 12.5; weight: Font.Medium; color: on ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.tab = modelData[0] }
                    }
                }
            }
        }

        UText {
            visible: root.list.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: DevDash.error !== "" ? DevDash.error
                : root.tab === "ci" ? "Add repos in this widget's options (github:owner/repo or gitea:owner/repo)"
                : "Nothing open. Nice."
            size: 13
            color: DevDash.error !== "" ? Theme.c.error : Theme.c.onSurfaceVariant
            topPadding: 6; bottomPadding: 6
        }

        Repeater {
            model: root.list.slice(0, root.rows)
            delegate: Item {
                required property var modelData
                width: column.width; height: 50
                Rectangle { anchors.fill: parent; radius: 14; color: Theme.c.onSurface; opacity: rowMouse.containsMouse ? 0.06 : 0 }
                Rectangle {
                    id: badge
                    x: 6; anchors.verticalCenter: parent.verticalCenter
                    width: 32; height: 32; radius: 16
                    color: Theme.c.surfaceContainerHighest
                    MIcon {
                        anchors.centerIn: parent
                        icon: root.tab === "ci" ? root.runIcon(modelData.status)[0] : (root.tab === "pr" ? Icons.merge : Icons.bug_report)
                        color: root.tab === "ci" ? root.runIcon(modelData.status)[1] : (modelData.review ? Theme.c.tertiary : Theme.c.primary)
                        size: 18; fill: root.tab === "ci" ? 1 : 0
                    }
                }
                Column {
                    anchors { left: badge.right; leftMargin: 10; right: meta.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                    UText { width: parent.width; text: root.tab === "ci" ? (modelData.name || modelData.repo) : modelData.title; size: 13.5; weight: Font.Medium }
                    UText {
                        width: parent.width
                        text: root.tab === "ci" ? modelData.repo + (modelData.branch ? "  ·  " + modelData.branch : "") + "  ·  " + modelData.status
                            : modelData.repo + " #" + modelData.number + (modelData.review ? "  ·  review requested" : "") + (modelData.draft ? "  ·  draft" : "")
                        size: 11.5; color: Theme.c.onSurfaceVariant
                    }
                }
                Column {
                    id: meta
                    anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                    Rectangle {
                        anchors.right: parent.right
                        height: 18; radius: 9; width: src.implicitWidth + 12
                        color: modelData.source === "gitea" ? Theme.c.tertiaryContainer : Theme.c.secondaryContainer
                        UText { id: src; anchors.centerIn: parent; text: modelData.source; size: 10.5; color: modelData.source === "gitea" ? Theme.c.onTertiaryContainer : Theme.c.onSecondaryContainer }
                    }
                    UText { anchors.right: parent.right; text: root.ago(modelData.updated); size: 11; color: Theme.c.onSurfaceVariant }
                }
                MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Desk.openUrl(modelData.url) }
            }
        }
    }
}
