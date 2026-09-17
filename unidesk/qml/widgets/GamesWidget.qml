import QtQuick
import QtQuick.Effects
import "../components"
import "../Icons.js" as Icons

// "Jump back in": your most recently played Steam / Epic / Riot games.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property int count: opt("count", 5)
    readonly property real coverW: opt("cover_width", 96)
    readonly property real coverH: coverW * 1.5
    readonly property var games: Games.recent.slice(0, count)

    implicitWidth: count * coverW + (count - 1) * 10 + 28
    implicitHeight: coverH + 76

    UText { x: 14; y: 12; text: root.opt("title", "Jump back in"); size: 17; weight: Font.Medium }

    UText {
        visible: root.games.length === 0
        anchors.centerIn: parent
        text: "Looking for your games…"
        size: 13; color: Theme.c.onSurfaceVariant
    }

    Row {
        x: 14; y: 48
        spacing: 10
        Repeater {
            model: root.games
            delegate: Item {
                id: game
                required property var modelData
                required property int index
                width: root.coverW; height: root.coverH + 18
                readonly property bool hovered: gameMouse.containsMouse

                Item {
                    id: cover
                    width: root.coverW; height: root.coverH
                    y: game.hovered ? -6 : 0
                    scale: gameMouse.pressed ? 0.96 : 1
                    Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                    Behavior on scale { NumberAnimation { duration: 120 } }

                    RectangularShadow {
                        anchors.fill: parent
                        radius: 16; blur: game.hovered ? 20 : 10; offset.y: game.hovered ? 8 : 3
                        color: Qt.rgba(0, 0, 0, 0.4)
                        visible: Theme.shadows
                    }
                    ShapedImage {
                        id: coverImage
                        anchors.fill: parent
                        radius: 16
                        visible: game.modelData.tall
                        source: game.modelData.tall ? game.modelData.cover : ""
                    }
                    Rectangle {
                        anchors.fill: parent
                        visible: game.modelData.tall && !coverImage.ready
                        radius: 16
                        color: Theme.c.secondaryContainer
                        UText {
                            anchors.centerIn: parent
                            width: parent.width - 16
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap; maximumLineCount: 3
                            text: game.modelData.name
                            size: 13; weight: Font.Medium
                            color: Theme.c.onSecondaryContainer
                        }
                    }
                    // Non-Steam games only have an icon: sit it on a tinted tile.
                    Rectangle {
                        anchors.fill: parent
                        visible: !game.modelData.tall
                        radius: 16
                        color: Theme.c.surfaceContainerHighest
                        Image {
                            anchors.centerIn: parent
                            width: parent.width * 0.55; height: width
                            source: game.modelData.tall ? "" : game.modelData.cover
                            sourceSize: Qt.size(128, 128)
                            smooth: true; mipmap: true
                        }
                    }
                    // play badge on hover
                    Item {
                        anchors.centerIn: parent
                        width: 44; height: 44
                        opacity: game.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 150 } }
                        MShape { anchors.fill: parent; shape: "flower"; color: Theme.c.primary }
                        MIcon { anchors.centerIn: parent; icon: Icons.play_arrow; fill: 1; size: 24; color: Theme.c.onPrimary }
                    }
                }
                UText {
                    anchors { top: cover.bottom; topMargin: 6; horizontalCenter: parent.horizontalCenter }
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: game.modelData.name
                    size: 11.5
                    color: game.hovered ? Theme.c.onSurface : Theme.c.onSurfaceVariant
                }
                MouseArea { id: gameMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Games.launch(game.index) }
            }
        }
    }
}
