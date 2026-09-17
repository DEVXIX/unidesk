import QtQuick
import "../components"
import "../Icons.js" as Icons

// One stat as a tile: big number, label, icon on a flower badge.
// Hover shows the detail (e.g. 12.4 / 32 GB).
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property string metric: opt("metric", "cpu")
    tone: opt("tone", "primary")
    radius: Theme.radius - 4

    readonly property var s: System.stats
    readonly property var info: {
        var g = s.gpu;
        switch (metric) {
        case "ram": return { icon: Icons.memory, value: s.ram, label: "RAM", unit: "%", detail: s.ramUsedGb.toFixed(1) + " / " + Math.round(s.ramTotalGb) + " GB" };
        case "disk": return { icon: Icons.hard_drive, value: s.disk, label: "Disk", unit: "%", detail: Math.round(s.diskFreeGb) + " GB free" };
        case "gpu": return { icon: Icons.developer_board, value: g ? g.load : 0, label: "GPU", unit: "%", detail: g ? g.name + " · " + Math.round(g.temp) + "°" : "No NVIDIA GPU" };
        case "cpu-temp": return { icon: Icons.thermostat, value: s.cpuTemp === null || s.cpuTemp === undefined ? 0 : s.cpuTemp, label: "CPU temp", unit: "\u00b0", detail: s.cpuTemp === null || s.cpuTemp === undefined ? "Needs LibreHardwareMonitor (web server on)" : s.cpuName };
        case "gpu-temp": return { icon: Icons.thermostat, value: g ? g.temp : 0, label: "GPU temp", unit: "°", detail: g ? g.name : "No NVIDIA GPU" };
        case "vram": return { icon: Icons.speed, value: g ? g.vram : 0, label: "VRAM", unit: "%", detail: g ? g.name : "No NVIDIA GPU" };
        default: return { icon: Icons.monitor_heart, value: s.cpu, label: "CPU", unit: "%", detail: s.cpuName.replace(/\(R\)|\(TM\)|CPU|Processor|\d+-Core/g, "").replace(/\s+/g, " ").trim() };
        }
    }

    implicitWidth: opt("width", 130)
    implicitHeight: opt("height", 118)

    Item {
        anchors.top: parent.top; anchors.right: parent.right
        anchors.margins: 12
        width: 38; height: 38
        MShape { anchors.fill: parent; shape: "flower"; color: root.onColor }
        MIcon { anchors.centerIn: parent; icon: root.info.icon; size: 20; fill: 1; color: root.color }
    }

    Column {
        anchors { left: parent.left; leftMargin: 14; right: parent.right; rightMargin: 10; bottom: parent.bottom; bottomMargin: 12 }
        spacing: -2
        UText {
            text: root.metric === "cpu-temp" && (root.s.cpuTemp === null || root.s.cpuTemp === undefined) ? "\u2014" : Math.round(root.info.value) + root.info.unit
            size: 28; weight: Font.DemiBold
            color: root.onColor
            font.features: { "tnum": 1 }
        }
        Item {
            width: parent.width; height: label.height
            UText {
                id: label
                width: parent.width
                text: root.info.label
                size: 15
                color: root.onColor
                opacity: hover.hovered ? 0 : 0.85
                Behavior on opacity { NumberAnimation { duration: 180 } }
            }
            UText {
                width: parent.width
                anchors.verticalCenter: label.verticalCenter
                text: root.info.detail
                size: 11.5
                color: root.onColor
                opacity: hover.hovered ? 0.9 : 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
            }
        }
    }

    HoverHandler { id: hover }
}
