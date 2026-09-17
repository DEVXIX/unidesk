import QtQuick
import "../components"
import "../Icons.js" as Icons

// Photos from a folder in an expressive frame, crossfading every few seconds.
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property real w: opt("width", opt("size", 360))
    readonly property real h: opt("height", opt("size", 360))
    readonly property string frameShape: opt("shape", "squircle") === "rounded" ? "" : opt("shape", "squircle")
    readonly property var images: {
        var list = Desk.listImages(opt("folder", "%USERPROFILE%\\Pictures"));
        if (opt("shuffle", true)) {
            list = list.slice();
            for (var i = list.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = list[i]; list[i] = list[j]; list[j] = t; }
        }
        return list;
    }
    property int index: 0
    property bool frontIsA: true

    function advance() {
        if (images.length < 2) return;
        index = (index + 1) % images.length;
        if (frontIsA) b.source = images[index]; else a.source = images[index];
    }

    Timer {
        interval: Math.max(3, root.opt("interval", 12)) * 1000
        running: root.images.length > 1 && !Desk.suspended
        repeat: true
        onTriggered: root.advance()
    }

    implicitWidth: w
    implicitHeight: h

    ShapedImage {
        id: a
        anchors.fill: parent
        shape: root.frameShape; radius: Theme.radius
        source: root.images.length ? root.images[0] : ""
        opacity: root.frontIsA ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 1200; easing.type: Easing.InOutQuad } }
        onReadyChanged: if (ready && !root.frontIsA && source == root.images[root.index]) root.frontIsA = true
    }
    ShapedImage {
        id: b
        anchors.fill: parent
        shape: root.frameShape; radius: Theme.radius
        opacity: root.frontIsA ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 1200; easing.type: Easing.InOutQuad } }
        onReadyChanged: if (ready && root.frontIsA && source == root.images[root.index]) root.frontIsA = false
    }

    Column {
        visible: root.images.length === 0
        anchors.centerIn: parent
        spacing: 6
        MIcon { anchors.horizontalCenter: parent.horizontalCenter; icon: Icons.photo_library; size: 32; color: Theme.c.primary }
        UText { anchors.horizontalCenter: parent.horizontalCenter; text: "No pictures in that folder"; size: 13; color: Theme.c.onSurfaceVariant }
    }

    MouseArea { anchors.fill: parent; enabled: root.images.length > 1; cursorShape: Qt.PointingHandCursor; onClicked: root.advance() }
}
