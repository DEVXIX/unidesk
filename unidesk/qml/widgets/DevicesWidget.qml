import QtQuick
import "../components"
import "../Icons.js" as Icons

// Battery levels: this PC (laptops) and Bluetooth devices that report one.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property var rows: {
        var out = [];
        if (Devices.pc) out.push({ name: "This PC", battery: Devices.pc.battery, icon: Devices.pc.charging ? Icons.battery_charging_full : Icons.battery_full });
        Devices.items.forEach(function (d) {
            var n = d.name.toLowerCase();
            var icon = /head|buds|airpods|audio|ear/.test(n) ? Icons.headphones : /mouse|mx /.test(n) ? Icons.mouse
                     : /controller|gamepad|xbox|dualsense|pad/.test(n) ? Icons.gamepad : /keyboard|keys/.test(n) ? Icons.keyboard : Icons.bluetooth;
            out.push({ name: d.name, battery: d.battery, icon: icon });
        });
        return out;
    }

    implicitWidth: opt("width", 320)
    implicitHeight: column.implicitHeight + 28

    Column {
        id: column
        x: 14; y: 14
        width: parent.width - 28
        spacing: 6

        UText { text: "Batteries"; size: 17; weight: Font.Medium; bottomPadding: 2 }

        UText {
            visible: root.rows.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: "No wireless devices are reporting a battery level right now"
            size: 13; color: Theme.c.onSurfaceVariant
        }

        Repeater {
            model: root.rows
            delegate: Item {
                required property var modelData
                readonly property bool low: modelData.battery <= 20
                width: column.width; height: 50
                Item {
                    id: badge
                    x: 4; anchors.verticalCenter: parent.verticalCenter
                    width: 36; height: 36
                    MShape { anchors.fill: parent; shape: "flower"; color: low ? Theme.c.errorContainer : Theme.c.secondaryContainer }
                    MIcon { anchors.centerIn: parent; icon: modelData.icon; size: 19; fill: 1; color: low ? Theme.c.onErrorContainer : Theme.c.onSecondaryContainer }
                }
                Column {
                    anchors { left: badge.right; leftMargin: 12; right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                    spacing: 5
                    Item {
                        width: parent.width; height: devName.height
                        UText { id: devName; width: parent.width - pct.width - 8; text: modelData.name; size: 13; weight: Font.Medium }
                        UText { id: pct; anchors.right: parent.right; text: modelData.battery + "%"; size: 12.5; color: low ? Theme.c.error : Theme.c.onSurfaceVariant }
                    }
                    Rectangle {
                        width: parent.width; height: 8; radius: 4
                        color: Theme.c.surfaceContainerHighest
                        Rectangle { width: parent.width * modelData.battery / 100; height: parent.height; radius: 4; color: low ? Theme.c.error : Theme.c.primary }
                    }
                }
            }
        }
    }
}
