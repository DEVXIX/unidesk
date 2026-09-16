import QtQuick
import QtQuick.Effects
import "../components"

// An image in an expressive frame. src: a file path, "wallpaper" or "artwork".
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real size: opt("size", 400)
    readonly property string src: String(opt("src", "wallpaper"))

    implicitWidth: opt("width", size)
    implicitHeight: opt("height", size)

    ShapedImage {
        anchors.fill: parent
        shape: root.opt("shape", "star") === "rounded" ? "" : root.opt("shape", "star")
        radius: Theme.radius
        source: root.src === "wallpaper" ? Desk.wallpaper
              : root.src === "artwork" ? (Media.playing && Media.playing.art ? Media.playing.art : Desk.wallpaper)
              : Desk.fileUrl(root.src)
        layer.enabled: Theme.shadows
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, 0.45)
            shadowBlur: 0.8
            shadowVerticalOffset: 6
        }
    }
}
