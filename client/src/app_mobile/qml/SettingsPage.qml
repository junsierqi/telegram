import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M120: settings hub. Each row pushes the matching sub-page onto the
// StackView. Kept deliberately flat; no nested settings sub-trees yet.
Page {
    id: page
    background: Rectangle { color: "#f4f5f7" }

    signal backRequested()
    signal openProfile()
    signal openContacts()
    signal openDevices()
    signal openRemote()
    signal openSearch()
    signal openAttachments()
    signal openCall()

    header: Rectangle {
        height: 56
        color: "#3390ec"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 12
            spacing: 6
            Button {
                background: Rectangle { color: "transparent" }
                contentItem: Label { text: "‹"; color: "white"; font.pointSize: 22 }
                onClicked: page.backRequested()
                Layout.preferredWidth: 36
            }
            Label {
                text: qsTr("Settings")
                color: "white"; font.bold: true; font.pointSize: 14
                Layout.fillWidth: true
            }
        }
    }

    ListView {
        anchors.fill: parent
        clip: true
        model: [
            { label: qsTr("Profile"),         signalName: "openProfile" },
            { label: qsTr("Contacts"),        signalName: "openContacts" },
            { label: qsTr("Devices"),         signalName: "openDevices" },
            { label: qsTr("Find users / search messages"), signalName: "openSearch" },
            { label: qsTr("Attachments"),     signalName: "openAttachments" },
            { label: qsTr("Remote control"),  signalName: "openRemote" },
            { label: qsTr("Voice / video call"), signalName: "openCall" }
        ]
        delegate: Rectangle {
            width: parent ? parent.width : 0
            height: 56
            color: ta.pressed ? "#e6e9ec" : "white"
            Rectangle {
                anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
                height: 1; color: "#eef0f2"
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16; anchors.rightMargin: 16
                Label {
                    text: modelData.label
                    color: "#0f1419"
                    font.pointSize: 13
                    Layout.fillWidth: true
                }
                Label { text: "›"; color: "#7c8a96"; font.pointSize: 18 }
            }
            TapHandler {
                id: ta
                onTapped: {
                    switch (modelData.signalName) {
                        case "openProfile":     page.openProfile(); break
                        case "openContacts":    page.openContacts(); break
                        case "openDevices":     page.openDevices(); break
                        case "openSearch":      page.openSearch(); break
                        case "openAttachments": page.openAttachments(); break
                        case "openRemote":      page.openRemote(); break
                        case "openCall":        page.openCall(); break
                    }
                }
            }
        }
    }
}
