import QtQuick
import "../components"

// This week (or the whole month) with today picked out.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property bool month: opt("view", "week") === "month"
    readonly property bool mondayFirst: opt("week_starts", "monday") !== "sunday"
    property date today: new Date()

    // Wake at midnight.
    function untilMidnight() {
        var n = new Date();
        return new Date(n.getFullYear(), n.getMonth(), n.getDate() + 1, 0, 0, 5) - n;
    }
    Timer {
        id: midnight
        running: true
        interval: root.untilMidnight()
        onTriggered: {
            root.today = new Date();
            interval = root.untilMidnight();
            start();
        }
    }

    readonly property var names: mondayFirst ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] : ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
    readonly property var days: {
        var t = today, out = [];
        var offset = (t.getDay() + (mondayFirst ? 6 : 0)) % 7;
        var start;
        if (month) {
            var first = new Date(t.getFullYear(), t.getMonth(), 1);
            start = new Date(first.getFullYear(), first.getMonth(), 1 - (first.getDay() + (mondayFirst ? 6 : 0)) % 7);
        } else {
            start = new Date(t.getFullYear(), t.getMonth(), t.getDate() - offset);
        }
        var count = month ? 42 : 7;
        for (var i = 0; i < count; i++) {
            var d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
            out.push({ n: d.getDate(), today: d.toDateString() === t.toDateString(), inMonth: d.getMonth() === t.getMonth() });
        }
        return out;
    }

    implicitWidth: opt("width", 280)
    implicitHeight: column.implicitHeight + 28

    Column {
        id: column
        x: 14; y: 14
        width: parent.width - 28
        spacing: 8

        Rectangle {
            height: 34
            width: title.implicitWidth + 28
            radius: 17
            color: Theme.c.primary
            UText {
                id: title
                anchors.centerIn: parent
                text: Qt.formatDate(root.today, "MMMM yyyy")
                size: 16; weight: Font.Medium
                color: Theme.c.onPrimary
            }
        }

        Grid {
            columns: 7
            width: parent.width
            readonly property real cell: width / 7
            Repeater {
                model: root.names
                UText {
                    required property string modelData
                    width: parent.cell; height: 26
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    text: modelData; size: 12.5; weight: Font.Medium
                    color: Theme.c.onSurfaceVariant
                }
            }
            Repeater {
                model: root.days
                Item {
                    required property var modelData
                    width: parent.cell; height: 32
                    Rectangle {
                        anchors.centerIn: parent
                        width: 30; height: 30; radius: 15
                        color: Theme.c.primary
                        visible: modelData.today
                    }
                    UText {
                        anchors.centerIn: parent
                        text: modelData.n
                        size: 13; weight: modelData.today ? Font.Bold : Font.Normal
                        color: modelData.today ? Theme.c.onPrimary : Theme.c.onSurface
                        opacity: modelData.inMonth ? 1 : 0.35
                    }
                }
            }
        }
    }
}
