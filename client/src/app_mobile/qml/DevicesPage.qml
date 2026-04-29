import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M120: list registered devices, revoke / trust per row.
Page {
    id: page
    background: Rectangle { color: "#f4f5f7" }

    signal backRequested()

    header: Rectangle {
        height: 56; color: "#3390ec"
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 12
            Button {
                background: Rectangle { color: "transparent" }
                contentItem: Label { text: "‹"; color: "white"; font.pointSize: 22 }
                onClicked: page.backRequested()
                Layout.preferredWidth: 36
            }
            Label {
                text: qsTr("Devices"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
            Button {
                text: qsTr("Refresh")
                onClicked: ChatBridge.refreshDevices()
            }
        }
    }

    Connections {
        target: ChatBridge
        function onDevicesReady(rows) {
            deviceList.model = rows
        }
    }

    Component.onCompleted: ChatBridge.refreshDevices()

    ListView {
        id: deviceList
        anchors.fill: parent
        clip: true
        delegate: Rectangle {
            width: deviceList.width; height: 76; color: "white"
            Rectangle {
                anchors.bottom: parent.bottom; anchors.left: parent.left
                anchors.right: parent.right; height: 1; color: "#eef0f2"
            }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 4
                RowLayout {
                    Layout.fillWidth: true; spacing: 6
                    Label {
                        text: modelData.label || modelData.deviceId
                        color: "#0f1419"; font.bold: true; font.pointSize: 13
                        Layout.fillWidth: true
                    }
                    Rectangle {
                        visible: modelData.active
                        width: 8; height: 8; radius: 4; color: "#7bc862"
                    }
                    Label {
                        visible: modelData.trusted
                        text: qsTr("trusted"); color: "#3390ec"
                        font.pointSize: 9; font.bold: true
                    }
                }
                Label {
                    text: modelData.platform + " · " + modelData.deviceId
                    color: "#7c8a96"; font.pointSize: 10
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 6
                    Item { Layout.fillWidth: true }
                    Button {
                        text: modelData.trusted ? qsTr("Untrust") : qsTr("Trust")
                        onClicked: ChatBridge.updateDeviceTrust(modelData.deviceId, !modelData.trusted)
                    }
                    Button {
                        text: qsTr("Revoke")
                        onClicked: ChatBridge.revokeDevice(modelData.deviceId)
                    }
                }
            }
        }
    }
}
