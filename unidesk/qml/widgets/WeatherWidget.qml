import QtQuick
import "../components"
import "../Icons.js" as Icons

Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    tone: opt("tone", "primary")
    readonly property var d: Weather.data
    readonly property bool metric: !d || d.units !== "imperial"
    readonly property var icons: ({
        sun: Icons.sunny, moon: Icons.clear_night, partly: Icons.partly_cloudy_day, cloud: Icons.cloud,
        fog: Icons.foggy, rain: Icons.rainy, snow: Icons.weather_snowy, storm: Icons.thunderstorm
    })

    implicitWidth: opt("width", 420)
    implicitHeight: 122

    UText {
        visible: !root.d
        anchors.centerIn: parent
        text: "Checking the sky…"
        color: root.onColor
        opacity: 0.7
    }

    Row {
        visible: !!root.d
        x: 16; y: 12
        spacing: 12
        UText {
            text: root.d ? Math.round(root.d.temp) + "°" + (root.metric ? "C" : "F") : ""
            size: 44; weight: Font.DemiBold
            color: root.onColor
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -2
            UText { text: root.d ? root.d.condition : ""; size: 17; color: root.onColor }
            UText { text: root.d ? root.d.place : ""; size: 14; color: root.onColor; opacity: 0.7 }
        }
    }

    Item {
        visible: !!root.d
        anchors { right: parent.right; top: parent.top; margins: 12 }
        width: 52; height: 52
        MShape { anchors.fill: parent; shape: "cookie12"; color: Theme.c.primary }
        MIcon { anchors.centerIn: parent; icon: root.d ? root.icons[root.d.icon] : ""; size: 28; fill: 1; color: Theme.c.onPrimary }
    }

    Row {
        visible: !!root.d
        anchors { left: parent.left; leftMargin: 16; bottom: parent.bottom; bottomMargin: 14 }
        spacing: 14
        Repeater {
            model: root.d ? [
                [Icons.water_drop, Math.round(root.d.humidity) + "%"],
                [Icons.cloud, Math.round(root.d.clouds) + "%"],
                [Icons.air, root.d.wind.toFixed(1) + (root.metric ? " m/s" : " mph")],
                [Icons.visibility, root.d.visibility.toFixed(1) + (root.metric ? " km" : " mi")]
            ] : []
            Row {
                required property var modelData
                spacing: 3
                MIcon { icon: modelData[0]; size: 14; color: root.onColor; opacity: 0.8; anchors.verticalCenter: parent.verticalCenter }
                UText { text: modelData[1]; size: 12; color: root.onColor; opacity: 0.85; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }

    Column {
        visible: !!root.d
        anchors { right: parent.right; rightMargin: 16; bottom: parent.bottom; bottomMargin: 10 }
        Repeater {
            model: root.d ? [[Icons.wb_twilight, root.d.sunrise], [Icons.bedtime, root.d.sunset]] : []
            Row {
                required property var modelData
                anchors.right: parent.right
                spacing: 3
                MIcon { icon: modelData[0]; size: 13; color: root.onColor; opacity: 0.8; anchors.verticalCenter: parent.verticalCenter }
                UText { text: modelData[1]; size: 11.5; color: root.onColor; opacity: 0.85 }
            }
        }
    }
}
