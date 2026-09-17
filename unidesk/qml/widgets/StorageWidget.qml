import QtQuick
import "../components"
import "../Icons.js" as Icons

// Every drive with a bar for how full it is. Click one to open it.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    tone: opt("tone", "surface")
    readonly property bool plain: ["surface", "high", "highest"].indexOf(tone) >= 0
    // "all", or the drive letters to show ("C D", "C:, D:").
    readonly property string letters: {
        var wanted = String(opt("drives", "all")).trim().toUpperCase();
        return wanted === "" || wanted === "ALL" ? "" : wanted.replace(/[^A-Z]/g, "");
    }
    readonly property var drives: letters === "" ? Storage.drives
        : Storage.drives.filter(function (d) { return letters.indexOf(d.letter.charAt(0).toUpperCase()) >= 0; })
    readonly property real totalFree: drives.reduce(function (sum, d) { return sum + d.free; }, 0)

    function size(bytes) {
        var units = ["B", "KB", "MB", "GB", "TB", "PB"], n = bytes || 0, i = 0;
        while (n >= 1000 && i < units.length - 1) { n /= 1024; i++; }
        return (i > 0 && n < 10 ? n.toFixed(1) : Math.round(n)) + " " + units[i];
    }

    implicitWidth: opt("width", 320)
    implicitHeight: column.implicitHeight + 28

    Column {
        id: column
        x: 14; y: 14
        width: parent.width - 28
        spacing: 10

        Item {
            width: parent.width; height: 34
            Rectangle {
                height: 34; radius: 17
                width: title.implicitWidth + 28
                color: root.plain ? Theme.c.primary : root.onColor
                UText { id: title; anchors.centerIn: parent; text: "Storage"; size: 15; weight: Font.Medium; color: root.plain ? Theme.c.onPrimary : root.color }
            }
            UText {
                anchors { right: parent.right; rightMargin: 4; verticalCenter: parent.verticalCenter }
                visible: root.drives.length > 1
                text: root.size(root.totalFree) + " free"
                size: 13
                color: root.onColor
                opacity: 0.75
            }
        }

        Repeater {
            model: root.drives
            Item {
                id: drive
                required property var modelData
                readonly property real used: Math.max(0, Math.min(1, modelData.percent / 100))
                readonly property bool full: modelData.percent >= 90
                width: column.width
                height: 58

                Rectangle {
                    anchors { fill: parent; leftMargin: -6; rightMargin: -6 }
                    radius: 16
                    color: root.onColor
                    opacity: driveMouse.containsMouse ? 0.07 : 0
                    Behavior on opacity { NumberAnimation { duration: 150 } }
                }
                Item {
                    id: badge
                    anchors.verticalCenter: parent.verticalCenter
                    width: 40; height: 40
                    MShape { anchors.fill: parent; shape: "cookie12"; color: root.plain ? Theme.c.secondaryContainer : Qt.alpha(root.onColor, 0.16) }
                    MIcon {
                        anchors.centerIn: parent
                        icon: drive.modelData.removable ? Icons.usb : Icons.hard_drive
                        size: 20; fill: 1
                        color: root.plain ? Theme.c.onSecondaryContainer : root.onColor
                    }
                }
                Column {
                    anchors { left: badge.right; leftMargin: 12; right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 5
                    Item {
                        width: parent.width; height: name.implicitHeight
                        UText {
                            id: name
                            width: parent.width - percent.implicitWidth - 8
                            text: drive.modelData.letter + (drive.modelData.label ? "  " + drive.modelData.label : "")
                            textFormat: Text.PlainText
                            size: 14.5; weight: Font.Medium
                            color: root.onColor
                        }
                        UText {
                            id: percent
                            anchors.right: parent.right
                            text: Math.round(drive.modelData.percent) + "%"
                            size: 13; weight: Font.Medium
                            color: drive.full ? Theme.c.error : root.onColor
                            font.features: { "tnum": 1 }
                        }
                    }
                    // Expressive bar: the used part, a small gap, then the rest.
                    Item {
                        id: bar
                        width: parent.width; height: 10
                        readonly property real split: width * drive.used
                        Rectangle {
                            width: Math.max(bar.height, bar.split - 3); height: bar.height; radius: bar.height / 2
                            color: drive.full ? Theme.c.error : root.plain ? Theme.c.primary : root.onColor
                            Behavior on width { NumberAnimation { duration: 600 * Theme.animationSpeed; easing.type: Easing.OutCubic } }
                        }
                        Rectangle {
                            x: Math.min(bar.width, Math.max(bar.height, bar.split - 3) + 6)
                            width: Math.max(0, bar.width - x); height: bar.height; radius: bar.height / 2
                            color: root.plain ? Theme.c.secondaryContainer : Qt.alpha(root.onColor, 0.2)
                        }
                    }
                    UText {
                        text: root.size(drive.modelData.free) + " free of " + root.size(drive.modelData.total)
                        size: 12
                        color: root.onColor
                        opacity: 0.7
                    }
                }
                MouseArea { id: driveMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Storage.open(drive.modelData.root) }
            }
        }

        UText {
            visible: root.drives.length === 0
            text: "No drives to show"
            color: root.onColor
            opacity: 0.7
        }
    }
}
