import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M121: list every attachment in the selected conversation; tap to fetch.
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
                text: qsTr("Attachments")
                color: "white"; font.bold: true; font.pointSize: 14
                Layout.fillWidth: true
            }
            Button {
                text: qsTr("Refresh")
                onClicked: list.model = ChatBridge.selectedAttachments()
            }
        }
    }

    Component.onCompleted: list.model = ChatBridge.selectedAttachments()

    Connections {
        target: ChatBridge
        function onStoreChanged() { list.model = ChatBridge.selectedAttachments() }
        function onAttachmentReady(id, name, mime, size) {
            statusLabel.text = qsTr("Fetched ") + name + " (" + size + " bytes)"
        }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0

        ListView {
            id: list
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            delegate: Rectangle {
                width: list.width; height: 64; color: ta.pressed ? "#eef0f2" : "white"
                Rectangle {
                    anchors.bottom: parent.bottom; anchors.left: parent.left
                    anchors.right: parent.right; height: 1; color: "#eef0f2"
                }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    spacing: 10
                    Rectangle {
                        Layout.preferredWidth: 40; Layout.preferredHeight: 40
                        radius: 8; color: "#65aadd"
                        Label {
                            anchors.centerIn: parent
                            text: (modelData.mimeType || "?").indexOf("image") === 0 ? "🖼" : "📄"
                            color: "white"; font.pointSize: 18
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 0
                        Label {
                            text: modelData.filename || modelData.attachmentId
                            color: "#0f1419"; font.bold: true; elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            text: modelData.mimeType + " · " + modelData.sizeBytes + " B · from " + modelData.sender
                            color: "#7c8a96"; font.pointSize: 10
                        }
                    }
                }
                TapHandler {
                    id: ta
                    onTapped: ChatBridge.fetchAttachment(modelData.attachmentId)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; height: 36; color: "#eef0f2"
            Label {
                id: statusLabel
                anchors.fill: parent; anchors.margins: 8
                color: "#3390ec"; font.pointSize: 10
                text: qsTr("Tap an attachment to fetch.")
            }
        }
    }
}
