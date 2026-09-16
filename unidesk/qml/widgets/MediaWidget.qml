import QtQuick
import QtQuick.Effects
import "../components"
import "../Icons.js" as Icons

// Now playing with synced lyrics. style: card (controls on top, lyrics
// below) or poster (blurred cover, lyrics beside the art, wavy seek bar).
Item {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property string style: opt("style", "card")
    readonly property real w: opt("width", 420)
    readonly property bool lyricsWanted: opt("lyrics", true)
    property bool lyricsOpen: lyricsWanted
    readonly property var lyr: Media.lyrics
    readonly property bool lyricsAvailable: !!lyr && (lyr.loading || (lyr.lines && lyr.lines.length > 0) || !!lyr.plain)
    readonly property bool lyricsShown: lyricsOpen && lyricsAvailable

    readonly property var p: Media.playing
    readonly property bool has: !!p
    readonly property bool isPlaying: has && p.status === "playing"
    property real position: 0

    function fmt(s) {
        s = Math.max(0, Math.floor(s || 0));
        var m = Math.floor(s / 60), r = s % 60;
        return m + ":" + (r < 10 ? "0" : "") + r;
    }
    function tick() {
        if (!has) { position = 0; return; }
        var pos = p.position + (isPlaying ? (Date.now() - p.updatedAt) / 1000 : 0);
        position = p.duration > 0 ? Math.min(p.duration, Math.max(0, pos)) : Math.max(0, pos);
    }
    onPChanged: tick()

    // 4x a second only while something plays and time is on screen.
    Timer {
        interval: 250
        running: root.isPlaying && !Desk.suspended
        repeat: true
        onTriggered: root.tick()
    }

    implicitWidth: w
    implicitHeight: loader.item ? loader.item.implicitHeight : 0

    Loader {
        id: loader
        width: root.w
        sourceComponent: !root.has ? idle : root.style === "poster" ? poster : card
    }

    // ---- nothing playing -------------------------------------------------------
    Component {
        id: idle
        Card {
            implicitHeight: 72
            Row {
                anchors.verticalCenter: parent.verticalCenter
                x: 16
                spacing: 12
                Item {
                    width: 44; height: 44
                    MShape { anchors.fill: parent; shape: "flower"; color: Theme.c.secondaryContainer }
                    MIcon { anchors.centerIn: parent; icon: Icons.music_note; size: 22; color: Theme.c.onSecondaryContainer }
                }
                UText { anchors.verticalCenter: parent.verticalCenter; text: "Nothing playing"; size: 16; color: Theme.c.onSurfaceVariant }
            }
        }
    }

    // ---- card ------------------------------------------------------------------
    Component {
        id: card
        Card {
            implicitHeight: top.height + (root.lyricsShown ? lyricsBox.height + 12 : 0)
            Behavior on implicitHeight { NumberAnimation { duration: 350 * Theme.animationSpeed; easing.type: Easing.OutCubic } }
            clip: true

            Item {
                id: top
                width: parent.width
                height: 140

                ShapedImage {
                    id: art
                    x: 10; y: 10
                    width: 120; height: 120
                    radius: Theme.radius - 8
                    source: root.p.art || ""
                }
                Column {
                    anchors { left: art.right; leftMargin: 16; right: parent.right; rightMargin: 16; top: parent.top; topMargin: 18 }
                    spacing: 2
                    UText { width: parent.width; text: root.p.title; size: 19; weight: Font.Medium }
                    UText { width: parent.width; text: root.p.artist; size: 14; color: Theme.c.onSurfaceVariant }
                }
                Row {
                    anchors { right: parent.right; rightMargin: 14; bottom: parent.bottom; bottomMargin: 14 }
                    spacing: 8
                    IconButton {
                        visible: root.lyricsWanted && root.lyricsAvailable
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons.lyrics; size: 36; fill: root.lyricsOpen ? 1 : 0
                        color: root.lyricsOpen ? Theme.c.secondaryContainer : "transparent"
                        iconColor: root.lyricsOpen ? Theme.c.onSecondaryContainer : Theme.c.onSurfaceVariant
                        onClicked: root.lyricsOpen = !root.lyricsOpen
                    }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons.skip_previous; size: 36; fill: 1
                        iconColor: Theme.c.onSurfaceVariant
                        onClicked: Media.previous()
                    }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        icon: root.isPlaying ? Icons.pause : Icons.play_arrow
                        size: 52; iconSize: 28; fill: 1; shape: "flower"
                        color: Theme.c.primary; iconColor: Theme.c.onPrimary
                        onClicked: Media.playPause()
                    }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        icon: Icons.skip_next; size: 36; fill: 1
                        iconColor: Theme.c.onSurfaceVariant
                        onClicked: Media.next()
                    }
                }
            }

            Rectangle {
                y: top.height
                x: 16; width: parent.width - 32; height: 1
                color: Theme.c.outlineVariant
                opacity: root.lyricsShown ? 0.6 : 0
            }

            LyricsView {
                id: lyricsBox
                y: top.height + 6
                x: 20; width: parent.width - 40
                lines: root.opt("lyric_lines", 7)
                fontSize: 15
                lyrics: Media.lyrics
                position: root.position
                duration: root.p.duration
                opacity: root.lyricsShown ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 300 } }
            }
        }
    }

    // ---- poster ----------------------------------------------------------------
    Component {
        id: poster
        Item {
            id: posterRoot
            implicitHeight: 300

            RectangularShadow {
                anchors.fill: parent
                visible: Theme.shadows
                radius: Theme.radius
                blur: 22; spread: -2; offset.y: 5
                color: Qt.rgba(0, 0, 0, 0.32)
            }

            Item {
                id: surface
                anchors.fill: parent
                layer.enabled: true
                layer.effect: MultiEffect {
                    maskEnabled: true
                    maskSource: posterMask
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1.0
                }

                Rectangle { anchors.fill: parent; color: Theme.c.surfaceContainer }
                Image {
                    id: blurSource
                    anchors.fill: parent
                    source: root.p.art || ""
                    fillMode: Image.PreserveAspectCrop
                    sourceSize: Qt.size(96, 96)
                    visible: false
                }
                MultiEffect {
                    anchors.fill: parent
                    source: blurSource
                    blurEnabled: true
                    blur: 1.0
                    blurMax: 48
                    saturation: 0.1
                    visible: blurSource.status === Image.Ready
                }
                Rectangle { anchors.fill: parent; color: Theme.c.surfaceContainer; opacity: 0.62 }

                ShapedImage {
                    id: pArt
                    x: 14; y: 14
                    width: 150; height: 150
                    radius: 18
                    source: root.p.art || ""
                }
                LyricsView {
                    visible: root.lyricsShown
                    anchors { left: pArt.right; leftMargin: 16; right: parent.right; rightMargin: 16; top: pArt.top }
                    height: pArt.height
                    lines: 6
                    fontSize: 14
                    align: Text.AlignLeft
                    lyrics: Media.lyrics
                    position: root.position
                    duration: root.p.duration
                }

                Column {
                    anchors { left: parent.left; leftMargin: 16; right: pause.left; rightMargin: 12; top: pArt.bottom; topMargin: 12 }
                    spacing: 0
                    UText { width: parent.width; text: root.p.title; size: 19; weight: Font.Medium }
                    UText { width: parent.width; text: root.p.artist; size: 13; color: Theme.c.onSurfaceVariant }
                    UText {
                        topPadding: 4
                        text: root.fmt(root.position) + " / " + root.fmt(root.p.duration)
                        size: 15; color: Theme.c.onSurfaceVariant
                        font.features: { "tnum": 1 }
                    }
                }
                Rectangle {
                    id: pause
                    anchors { right: parent.right; rightMargin: 16; top: pArt.bottom; topMargin: 18 }
                    width: 50; height: 50; radius: 16
                    color: Theme.c.surfaceContainerHighest
                    IconButton {
                        anchors.centerIn: parent
                        size: 50; iconSize: 26; fill: 1
                        icon: root.isPlaying ? Icons.pause : Icons.play_arrow
                        onClicked: Media.playPause()
                    }
                }

                Row {
                    anchors { left: parent.left; leftMargin: 8; right: parent.right; rightMargin: 8; bottom: parent.bottom; bottomMargin: 6 }
                    spacing: 4
                    IconButton { id: prevBtn; icon: Icons.skip_previous; size: 32; fill: 1; iconColor: Theme.c.onSurfaceVariant; onClicked: Media.previous() }
                    WavySlider {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - prevBtn.width * 3 - parent.spacing * 3
                        value: root.p.duration > 0 ? root.position / root.p.duration : 0
                        playing: root.isPlaying
                        phase: root.position * 2.2
                        activeColor: Theme.c.onSurface
                        trackColor: Qt.alpha(Theme.c.onSurface, 0.3)
                        onSeek: (f) => Media.seek(f * root.p.duration)
                    }
                    IconButton { icon: Icons.skip_next; size: 32; fill: 1; iconColor: Theme.c.onSurfaceVariant; onClicked: Media.next() }
                    IconButton {
                        icon: Icons.lyrics; size: 32; fill: root.lyricsOpen ? 1 : 0
                        iconColor: root.lyricsOpen ? Theme.c.primary : Theme.c.onSurfaceVariant
                        onClicked: root.lyricsOpen = !root.lyricsOpen
                    }
                }
            }

            Rectangle {
                id: posterMask
                anchors.fill: parent
                radius: Theme.radius
                layer.enabled: true
                visible: false
            }
        }
    }
}
