import QtQuick

// Synced lyrics: the current line is bright and centred (or at the top for
// align: left), neighbours fade out with distance, and the column glides.
Item {
    id: root
    property var lyrics: ({})         // { lines: [{time, text}], plain, loading }
    property real position: 0
    property real duration: 0
    property int lines: 7
    property real fontSize: 15
    property int align: Text.AlignHCenter
    property color color: Theme.c.onSurface

    readonly property var list: (lyrics && lyrics.lines) ? lyrics.lines : []
    readonly property bool synced: list.length > 0
    readonly property real lineHeight: fontSize * 1.75

    implicitHeight: lines * lineHeight
    clip: true

    readonly property int active: {
        if (!synced) return -1;
        var t = position + 0.3, lo = 0, hi = list.length - 1, ans = -1;
        while (lo <= hi) {
            var mid = (lo + hi) >> 1;
            if (list[mid].time <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
        }
        return ans;
    }

    Column {
        id: column
        width: parent.width
        visible: root.synced
        y: {
            var item = repeater.itemAt(Math.max(0, root.active));
            if (!item) return root.height / 2;
            var anchor = root.align === Text.AlignHCenter ? root.height / 2 : root.lineHeight * 1.5;
            return Math.round(anchor - item.y - item.height / 2);
        }
        Behavior on y { NumberAnimation { duration: 520 * Theme.animationSpeed; easing.type: Easing.OutCubic } }

        Repeater {
            id: repeater
            model: root.list
            delegate: UText {
                required property var modelData
                required property int index
                readonly property int distance: root.active < 0 ? 3 : Math.abs(index - root.active)
                width: column.width
                topPadding: root.fontSize * 0.28
                bottomPadding: root.fontSize * 0.28
                text: modelData.text || "♪"
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                maximumLineCount: 2
                horizontalAlignment: root.align
                size: root.fontSize
                weight: distance === 0 ? Font.DemiBold : Font.Normal
                color: root.color
                // Lines that would sit on the clipped edge fade out entirely.
                readonly property int reach: root.align === Text.AlignHCenter ? Math.floor(root.lines / 2) : (index < root.active ? 1 : root.lines - 2)
                opacity: distance > reach ? 0 : [1, 0.62, 0.4, 0.24][Math.min(distance, 3)]
                scale: distance === 0 ? 1 : 0.92
                transformOrigin: root.align === Text.AlignHCenter ? Item.Center : Item.Left
                Behavior on opacity { NumberAnimation { duration: 400 } }
                Behavior on scale { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
            }
        }
    }

    // Unsynced lyrics: scroll through them with the song.
    UText {
        visible: !root.synced && !!(root.lyrics && root.lyrics.plain)
        width: parent.width
        y: -Math.max(0, implicitHeight - root.height) * (root.duration > 0 ? root.position / root.duration : 0)
        text: (root.lyrics && root.lyrics.plain) || ""
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        horizontalAlignment: root.align
        size: root.fontSize * 0.9
        color: root.color
        opacity: 0.7
        lineHeight: 1.35
        Behavior on y { NumberAnimation { duration: 1000 } }
    }

    UText {
        visible: !root.synced && !(root.lyrics && root.lyrics.plain)
        anchors.centerIn: parent
        width: parent.width
        horizontalAlignment: root.align
        text: root.lyrics && root.lyrics.loading ? "Finding lyrics…" : "No lyrics for this one"
        size: root.fontSize * 0.9
        color: root.color
        opacity: 0.45
    }
}
