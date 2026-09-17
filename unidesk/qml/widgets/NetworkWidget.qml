import QtQuick
import QtQuick.Shapes
import "../components"
import "../Icons.js" as Icons

// Download and upload speed right now, and the last minute as a soft graph.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    tone: opt("tone", "surface")
    readonly property bool bits: opt("units", "bytes") === "bits"
    readonly property bool graph: opt("graph", true)
    readonly property var s: Network.stats
    readonly property bool plain: ["surface", "high", "highest"].indexOf(tone) >= 0
    readonly property color downColor: plain ? Theme.c.primary : root.onColor
    readonly property color upColor: plain ? Theme.c.tertiary : Qt.alpha(root.onColor, 0.55)

    function speed(bytesPerSecond) {
        var n = (bytesPerSecond || 0) * (bits ? 8 : 1), step = bits ? 1000 : 1024, i = 0;
        var units = bits ? ["b/s", "Kb/s", "Mb/s", "Gb/s"] : ["B/s", "KB/s", "MB/s", "GB/s"];
        while (n >= 1000 && i < units.length - 1) { n /= step; i++; }
        return { value: i === 0 ? String(Math.round(n)) : n < 10 ? n.toFixed(1) : String(Math.round(n)), unit: units[i] };
    }
    // SVG path for a history, newest on the right; `area` closes it along the bottom.
    function trace(values, w, h, peak, area) {
        var n = values ? values.length : 0, slots = 60;
        if (n < 2 || w <= 0) return "M0 " + h + " L" + w + " " + h;
        var step = w / (slots - 1), x0 = w - (n - 1) * step, d = area ? "M" + x0.toFixed(1) + " " + h : "";
        for (var i = 0; i < n; i++) {
            var x = x0 + i * step, y = h - 1.5 - Math.min(1, values[i] / peak) * (h - 4);
            d += (i === 0 && !area ? "M" : " L") + x.toFixed(1) + " " + y.toFixed(1);
        }
        return area ? d + " L" + w + " " + h + " Z" : d;
    }

    implicitWidth: opt("width", 320)
    implicitHeight: graph ? 170 : 90

    Row {
        id: readout
        x: 16; y: 16
        width: parent.width - 32
        spacing: 12
        Repeater {
            model: [
                { icon: Icons.arrow_downward, label: "Download", value: root.s.down, color: root.downColor, on: Theme.c.onPrimary },
                { icon: Icons.arrow_upward, label: "Upload", value: root.s.up, color: root.upColor, on: Theme.c.onTertiary }
            ]
            Row {
                required property var modelData
                readonly property var shown: root.speed(modelData.value)
                width: (readout.width - readout.spacing) / 2
                spacing: 10
                Item {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 40; height: 40
                    MShape { anchors.fill: parent; shape: "cookie12"; color: modelData.color }
                    MIcon { anchors.centerIn: parent; icon: modelData.icon; size: 21; color: root.plain ? modelData.on : root.color }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    Row {
                        spacing: 4
                        UText { id: amount; text: shown.value; size: 25; weight: Font.DemiBold; color: root.onColor; font.features: { "tnum": 1 } }
                        UText { anchors.baseline: amount.baseline; text: shown.unit; size: 13; color: root.onColor; opacity: 0.75 }
                    }
                    UText { text: modelData.label; size: 12.5; color: root.onColor; opacity: 0.7 }
                }
            }
        }
    }

    Item {
        id: chart
        visible: root.graph
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 16; rightMargin: 16; bottomMargin: 16 }
        height: 64
        // A little headroom, and a floor so an idle connection stays a quiet line.
        readonly property real peak: {
            var top = 16 * 1024, down = root.s.downHistory || [], up = root.s.upHistory || [];
            for (var i = 0; i < down.length; i++) top = Math.max(top, down[i]);
            for (var j = 0; j < up.length; j++) top = Math.max(top, up[j]);
            return top * 1.15;
        }

        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.onColor; opacity: 0.12 }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: 0
                strokeColor: "transparent"
                fillColor: Qt.alpha(root.downColor, 0.2)
                PathSvg { path: root.trace(root.s.downHistory, chart.width, chart.height, chart.peak, true) }
            }
            ShapePath {
                strokeWidth: 2
                strokeColor: root.downColor
                fillColor: "transparent"
                joinStyle: ShapePath.RoundJoin
                capStyle: ShapePath.RoundCap
                PathSvg { path: root.trace(root.s.downHistory, chart.width, chart.height, chart.peak, false) }
            }
            ShapePath {
                strokeWidth: 2
                strokeColor: root.upColor
                fillColor: "transparent"
                joinStyle: ShapePath.RoundJoin
                capStyle: ShapePath.RoundCap
                PathSvg { path: root.trace(root.s.upHistory, chart.width, chart.height, chart.peak, false) }
            }
        }
    }
}
