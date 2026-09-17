import QtQuick
import QtQuick.Shapes
import "../components"
import "../Icons.js" as Icons

// League of Legends: rank, LP, win rate, streak and the last games, read from
// the League client (shows the last seen numbers while it's closed).
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    readonly property var d: League.data
    // "Preview rank" fakes a tier to see how each one looks.
    readonly property string preview: String(opt("preview_tier", "off"))
    readonly property bool previewing: preview !== "off" && preview !== ""
    readonly property bool apexPreview: ["Master", "Grandmaster", "Challenger"].indexOf(preview) >= 0
    readonly property var realQ: d ? (opt("queue", "solo") === "flex" ? d.flex : d.solo) : null
    readonly property var q: previewing
        ? { tier: preview, division: apexPreview ? "" : "I", lp: opt("preview_lp", apexPreview ? 1287 : 75), wins: 214, losses: 151 }
        : realQ
    readonly property string tierName: q ? q.tier : "Unranked"
    readonly property bool apex: ["Master", "Grandmaster", "Challenger"].indexOf(tierName) >= 0
    // [main colour, second colour for the ring gradient]
    readonly property var tierColors: ({
        Iron: ["#6d6461", "#4a4240"], Bronze: ["#b0703f", "#6e4128"], Silver: ["#a9b6c0", "#6f7d88"],
        Gold: ["#e3b04b", "#a8781f"], Platinum: ["#4fc1ad", "#2b7f76"], Emerald: ["#35c77a", "#16804a"],
        Diamond: ["#6f9bff", "#b77cff"], Master: ["#b06be6", "#ff7ad9"], Grandmaster: ["#ef4f55", "#ff9a52"],
        Challenger: ["#f6cf62", "#59c2ff"], Unranked: [Theme.c.outline, Theme.c.outlineVariant]
    })
    readonly property var tint: tierColors[tierName] || tierColors.Unranked
    readonly property int games: q ? q.wins + q.losses : 0

    implicitWidth: opt("width", 390)
    implicitHeight: d || previewing ? column.implicitHeight + 28 : 110

    Shape {
        id: ring
        visible: root.tierName !== "Unranked"
        anchors.fill: parent
        anchors.margins: -3
        preferredRendererType: Shape.CurveRenderer
        property real spin: 135
        ShapePath {
            strokeColor: "transparent"
            fillRule: ShapePath.OddEvenFill
            fillGradient: ConicalGradient {
                centerX: ring.width / 2; centerY: ring.height / 2
                angle: ring.spin
                GradientStop { position: 0.0; color: root.tint[0] }
                GradientStop { position: 0.5; color: root.tint[1] }
                GradientStop { position: 1.0; color: root.tint[0] }
            }
            PathRectangle { x: 0; y: 0; width: ring.width; height: ring.height; radius: root.radius + 3 }
            PathRectangle { x: 3; y: 3; width: ring.width - 6; height: ring.height - 6; radius: root.radius }
        }
    }

    Column {
        visible: !root.d && !root.previewing
        anchors.centerIn: parent
        spacing: 6
        MIcon { anchors.horizontalCenter: parent.horizontalCenter; icon: Icons.sports_esports; size: 28; color: Theme.c.primary }
        UText { anchors.horizontalCenter: parent.horizontalCenter; text: "Open the League client once to load your stats"; size: 13; color: Theme.c.onSurfaceVariant }
    }

    Column {
        id: column
        visible: !!root.d || root.previewing
        x: 14; y: 14
        width: parent.width - 28
        spacing: 12

        Item {
            width: parent.width; height: 52
            ShapedImage { id: icon; width: 52; height: 52; shape: "cookie12"; source: root.d ? root.d.icon : "" }
            Column {
                anchors { left: icon.right; leftMargin: 12; verticalCenter: parent.verticalCenter }
                Row {
                    spacing: 4
                    UText { text: root.d ? root.d.name : ""; size: 17; weight: Font.Medium }
                    UText { text: root.d && root.d.tag ? "#" + root.d.tag : ""; size: 14; color: Theme.c.onSurfaceVariant; anchors.baseline: parent.children[0].baseline }
                }
                UText {
                    text: root.d ? "Level " + root.d.level + (root.d.live ? "" : "  ·  last seen") : ""
                    size: 12; color: Theme.c.onSurfaceVariant
                }
            }
            Rectangle {
                visible: !!root.d && Math.abs(root.d.streak) >= 2
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                height: 30; radius: 15; width: streakRow.implicitWidth + 20
                color: root.d && root.d.streak > 0 ? Theme.c.primaryContainer : Theme.c.errorContainer
                Row {
                    id: streakRow
                    anchors.centerIn: parent; spacing: 4
                    MIcon { icon: root.d && root.d.streak > 0 ? Icons.trending_up : Icons.trending_down; size: 16; color: root.d && root.d.streak > 0 ? Theme.c.onPrimaryContainer : Theme.c.onErrorContainer; anchors.verticalCenter: parent.verticalCenter }
                    UText { text: root.d ? Math.abs(root.d.streak) + (root.d.streak > 0 ? " wins" : " losses") : ""; size: 12.5; weight: Font.Medium; color: root.d && root.d.streak > 0 ? Theme.c.onPrimaryContainer : Theme.c.onErrorContainer; anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }

        Rectangle {
            width: parent.width; height: 84; radius: 20
            color: Theme.c.secondaryContainer
            Item {
                id: emblem
                x: 12; anchors.verticalCenter: parent.verticalCenter
                width: 72; height: 72
                // Riot's ranked emblem (CommunityDragon, the same file the client shows).
                Image {
                    id: emblemImage
                    anchors.centerIn: parent
                    width: 88; height: 88  // pre-cropped around the crest by the League provider
                    visible: root.tierName !== "Unranked" && status === Image.Ready
                    source: root.tierName !== "Unranked" ? League.emblem(root.tierName) : ""
                    fillMode: Image.PreserveAspectFit
                    smooth: true; mipmap: true
                    cache: true
                    asynchronous: true
                }
                MIcon {
                    anchors.centerIn: parent
                    visible: !emblemImage.visible
                    icon: Icons.emoji_events; size: 30
                    color: Theme.c.onSecondaryContainer
                }
            }
            Column {
                anchors { left: emblem.right; leftMargin: 14; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                spacing: 4
                Item {
                    width: parent.width; height: tier.height
                    UText { id: tier; text: root.q ? root.q.tier + " " + root.q.division : ""; size: 20; weight: Font.DemiBold; color: Theme.c.onSecondaryContainer }
                    UText { anchors { right: parent.right; baseline: tier.baseline } text: root.q && root.q.tier !== "Unranked" ? root.q.lp + " LP" : ""; size: 14; color: Theme.c.onSecondaryContainer }
                }
                Rectangle {
                    width: parent.width; height: 8; radius: 4
                    color: Qt.alpha(Theme.c.onSecondaryContainer, 0.15)
                    Rectangle {
                        width: parent.width * (root.apex ? 1 : Math.min(1, root.q ? root.q.lp / 100 : 0)); height: parent.height; radius: 4
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: root.tierName === "Unranked" ? Theme.c.onSecondaryContainer : root.tint[0] }
                            GradientStop { position: 1; color: root.tierName === "Unranked" ? Theme.c.onSecondaryContainer : root.tint[1] }
                        }
                    }
                }
                UText {
                    text: root.previewing ? "Preview  \u00b7  " + root.q.wins + "W " + root.q.losses + "L  \u00b7  59% win rate"
                        : root.games > 0 ? root.q.wins + "W " + root.q.losses + "L  ·  " + Math.round(100 * root.q.wins / root.games) + "% win rate" : (root.opt("queue", "solo") === "flex" ? "Flex" : "Solo/Duo") + "  ·  no ranked games yet"
                    size: 12; color: Theme.c.onSecondaryContainer; opacity: 0.85
                }
            }
        }

        Row {
            spacing: 6
            Repeater {
                model: root.d ? root.d.games.slice(0, root.opt("games", 7)) : []
                delegate: Item {
                    required property var modelData
                    width: 42; height: 56
                    Rectangle {
                        width: 42; height: 42; radius: 21
                        color: modelData.win ? Theme.c.primary : Theme.c.error
                        ShapedImage { anchors.centerIn: parent; width: 36; height: 36; shape: "circle"; source: modelData.champion }
                    }
                    UText {
                        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom }
                        text: modelData.kills + "/" + modelData.deaths + "/" + modelData.assists
                        size: 9.5; color: Theme.c.onSurfaceVariant
                    }
                }
            }
        }
    }
}
