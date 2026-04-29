import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M120: list contacts + add/remove by user_id.
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
                text: qsTr("Contacts"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
            Button {
                text: qsTr("Refresh")
                onClicked: ChatBridge.refreshContacts()
            }
        }
    }

    Connections {
        target: ChatBridge
        function onContactsReady(rows) {
            contactList.model = rows
        }
    }

    Component.onCompleted: ChatBridge.refreshContacts()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ListView {
            id: contactList
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            delegate: Rectangle {
                width: contactList.width; height: 56
                color: "white"
                Rectangle {
                    anchors.bottom: parent.bottom; anchors.left: parent.left
                    anchors.right: parent.right; height: 1; color: "#eef0f2"
                }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    spacing: 10
                    Rectangle {
                        Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 18
                        color: modelData.online ? "#7bc862" : "#a695e7"
                        Label {
                            anchors.centerIn: parent
                            text: (modelData.displayName || modelData.userId || "?").substring(0, 1).toUpperCase()
                            color: "white"; font.bold: true
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 0
                        Label {
                            text: modelData.displayName || modelData.userId
                            color: "#0f1419"; font.bold: true; font.pointSize: 13
                        }
                        Label {
                            text: modelData.online ? qsTr("online") : modelData.userId
                            color: "#7c8a96"; font.pointSize: 10
                        }
                    }
                    Button {
                        text: qsTr("Remove")
                        onClicked: ChatBridge.removeContact(modelData.userId)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; height: 64; color: "white"
            border.color: "#eef0f2"; border.width: 1
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                spacing: 8
                TextField {
                    id: addField
                    placeholderText: qsTr("user_id to add")
                    Layout.fillWidth: true
                }
                Button {
                    text: qsTr("Add"); enabled: addField.text.trim().length > 0
                    onClicked: {
                        ChatBridge.addContact(addField.text.trim())
                        addField.text = ""
                    }
                }
            }
        }
    }
}
