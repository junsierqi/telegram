import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M121: combined user search + in-conversation message search.
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
                text: qsTr("Search"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
        }
    }

    Connections {
        target: ChatBridge
        function onSearchUsersReady(rows) { userList.model = rows }
        function onSearchMessagesReady(rows) { msgList.model = rows }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12; spacing: 10

        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: qsTr("Users") }
            TabButton { text: qsTr("Messages (selected chat)") }
        }

        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true; Layout.fillHeight: true

            ColumnLayout {
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    TextField {
                        id: userQuery
                        Layout.fillWidth: true
                        placeholderText: qsTr("username / display name / user_id")
                    }
                    Button {
                        text: qsTr("Find")
                        onClicked: ChatBridge.searchUsers(userQuery.text.trim())
                    }
                }
                ListView {
                    id: userList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    delegate: Rectangle {
                        width: userList.width; height: 56; color: "white"
                        Rectangle {
                            anchors.bottom: parent.bottom; anchors.left: parent.left
                            anchors.right: parent.right; height: 1; color: "#eef0f2"
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10
                            Label {
                                text: (modelData.displayName || modelData.username) + (modelData.online ? " · online" : "")
                                color: "#0f1419"; font.bold: true
                            }
                            Label {
                                text: "@" + modelData.username + " · " + modelData.userId
                                color: "#7c8a96"; font.pointSize: 10
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    TextField {
                        id: msgQuery
                        Layout.fillWidth: true
                        placeholderText: qsTr("search in selected conversation")
                    }
                    Button {
                        text: qsTr("Find")
                        enabled: ChatBridge.selectedConversationId.length > 0
                        onClicked: ChatBridge.searchMessages(msgQuery.text.trim())
                    }
                }
                ListView {
                    id: msgList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    delegate: Rectangle {
                        width: msgList.width; height: 64; color: "white"
                        Rectangle {
                            anchors.bottom: parent.bottom; anchors.left: parent.left
                            anchors.right: parent.right; height: 1; color: "#eef0f2"
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10
                            Label {
                                text: modelData.snippet
                                color: "#0f1419"; wrapMode: Text.WrapAnywhere
                                Layout.fillWidth: true; elide: Text.ElideRight
                                maximumLineCount: 2
                            }
                            Label {
                                text: modelData.sender + " · " + modelData.messageId
                                color: "#7c8a96"; font.pointSize: 10
                            }
                        }
                    }
                }
            }
        }
    }
}
