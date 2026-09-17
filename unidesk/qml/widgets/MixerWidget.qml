import QtQuick
import QtQuick.Controls.Basic
import "../components"
import "../Icons.js" as Icons

// Volume mixer: master volume, then one slider per app playing sound.
Card {
    id: root
    property var options: ({})
    function opt(k, d) { return options && options[k] !== undefined ? options[k] : d; }

    implicitWidth: opt("width", 360)
    implicitHeight: column.implicitHeight + 28

    Column {
        id: column
        x: 14; y: 14
        width: parent.width - 28
        spacing: 6

        Item {
            width: parent.width; height: 34
            Column {
                anchors.verticalCenter: parent.verticalCenter
                UText { text: "Sound"; size: 17; weight: Font.Medium }
                UText { width: column.width - 50; text: Audio.device; size: 11.5; color: Theme.c.onSurfaceVariant }
            }
            IconButton { anchors { right: parent.right; verticalCenter: parent.verticalCenter } icon: Icons.settings; size: 32; iconSize: 18; iconColor: Theme.c.onSurfaceVariant; onClicked: Audio.openSoundSettings() }
        }

        // master
        Rectangle {
            width: parent.width; height: 58; radius: 18
            color: Theme.c.primaryContainer
            IconButton {
                id: masterMute
                x: 8; anchors.verticalCenter: parent.verticalCenter
                icon: Audio.muted || Audio.master === 0 ? Icons.volume_off : Icons.headphones
                size: 40; iconSize: 22; fill: 1
                iconColor: Theme.c.onPrimaryContainer
                onClicked: Audio.toggleMute()
            }
            VolumeSlider {
                anchors { left: masterMute.right; leftMargin: 6; right: masterPct.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                value: Audio.master
                activeColor: Theme.c.onPrimaryContainer
                trackColor: Qt.alpha(Theme.c.onPrimaryContainer, 0.2)
                onMoved2: (v) => Audio.setMaster(v)
            }
            UText {
                id: masterPct
                anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                width: 36; horizontalAlignment: Text.AlignRight
                text: Math.round(Audio.master * 100)
                size: 14; weight: Font.DemiBold; color: Theme.c.onPrimaryContainer
                font.features: { "tnum": 1 }
            }
        }

        // A fixed number of rows so the card never grows into its neighbours;
        // more apps scroll.
        ListView {
            id: appList
            readonly property int rows: root.opt("rows", 3)
            width: column.width
            height: rows * 50
            clip: true
            model: Audio.sessions
            boundsBehavior: Flickable.StopAtBounds
            interactive: count > rows
            ScrollIndicator.vertical: ScrollIndicator {}
            delegate: Item {
                required property var modelData
                width: appList.width - (appList.count > appList.rows ? 6 : 0); height: 50
                Image {
                    id: appIcon
                    x: 6; anchors.verticalCenter: parent.verticalCenter
                    width: 28; height: 28
                    source: modelData.icon
                    sourceSize: Qt.size(56, 56)
                    smooth: true; mipmap: true
                    opacity: modelData.muted ? 0.4 : 1
                }
                UText {
                    id: name
                    anchors { left: appIcon.right; leftMargin: 10; top: parent.top; topMargin: 4 }
                    width: 120
                    text: modelData.name
                    size: 12.5
                    color: modelData.active ? Theme.c.onSurface : Theme.c.onSurfaceVariant
                }
                VolumeSlider {
                    anchors { left: appIcon.right; leftMargin: 6; right: mute.left; rightMargin: 4; bottom: parent.bottom; bottomMargin: -2 }
                    height: 26
                    value: modelData.volume
                    enabled: !modelData.muted
                    opacity: modelData.muted ? 0.45 : 1
                    onMoved2: (v) => Audio.setVolume(modelData.pid, v)
                }
                IconButton {
                    id: mute
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    icon: modelData.muted ? Icons.volume_off : Icons.volume_up
                    size: 32; iconSize: 17
                    iconColor: modelData.muted ? Theme.c.error : Theme.c.onSurfaceVariant
                    onClicked: Audio.toggleAppMute(modelData.pid)
                }
            }
        }

        UText {
            visible: Audio.sessions.length > appList.rows
            text: "Scroll for " + (Audio.sessions.length - appList.rows) + " more"
            size: 11.5; color: Theme.c.onSurfaceVariant
            leftPadding: 6
        }

        UText {
            visible: Audio.sessions.length === 0
            text: "No apps are playing sound"
            size: 13; color: Theme.c.onSurfaceVariant
            topPadding: 6; bottomPadding: 4
        }
    }
}
