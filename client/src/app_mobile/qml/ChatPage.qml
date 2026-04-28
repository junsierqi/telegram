import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: page
    background: Rectangle { color: "#e6ebee" }

    signal backRequested()

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
            ColumnLayout {
                Layout.fillWidth: true
                Label {
                    text: ChatBridge.selectedConversationId
                    color: "white"
                    font.bold: true
                    font.pointSize: 14
                }
                Label {
                    text: qsTr("online")
                    color: "#cee9ff"
                    font.pointSize: 9
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ListView {
            id: messageView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 6
            verticalLayoutDirection: ListView.TopToBottom
            onCountChanged: positionViewAtEnd()
            delegate: Item {
                width: messageView.width
                height: bubble.implicitHeight + 12
                Rectangle {
                    id: bubble
                    radius: 14
                    color: modelData.failed ? "#ffd7cf"
                          : modelData.outgoing ? "#eeffde" : "#ffffff"
                    border.color: modelData.pending ? "#b88a16" : "transparent"
                    border.width: modelData.pending ? 1 : 0
                    width: Math.min(parent.width * 0.78, contentLabel.implicitWidth + 24)
                    implicitHeight: contentLabel.implicitHeight + metaLabel.implicitHeight + 18
                    anchors {
                        right: modelData.outgoing ? parent.right : undefined
                        left: modelData.outgoing ? undefined : parent.left
                        rightMargin: 10
                        leftMargin: 10
                        verticalCenter: parent.verticalCenter
                    }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2
                        Label {
                            id: metaLabel
                            text: modelData.sender + (modelData.pending ? "  (sending)" :
                                  modelData.failed ? "  (failed)" : "")
                            color: "#7c8a96"
                            font.pointSize: 9
                        }
                        Label {
                            id: contentLabel
                            text: modelData.text
                            color: "#0f1419"
                            font.pointSize: 12
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "white"
            border.color: "#e6e8eb"
            border.width: 0
            Rectangle {
                anchors { top: parent.top; left: parent.left; right: parent.right }
                height: 1
                color: "#e6e8eb"
            }
            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                TextField {
                    id: composer
                    Layout.fillWidth: true
                    placeholderText: qsTr("Message")
                    Keys.onReturnPressed: sendButton.clicked()
                    background: Rectangle {
                        radius: 18
                        color: "#f4f5f7"
                        border.color: composer.activeFocus ? "#3390ec" : "#e6e8eb"
                        border.width: 1
                    }
                }
                Button {
                    id: sendButton
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    background: Rectangle {
                        radius: 22
                        color: sendButton.down ? "#2079d2" : "#3390ec"
                    }
                    contentItem: Label {
                        text: "↑"
                        color: "white"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.bold: true
                        font.pointSize: 18
                    }
                    onClicked: {
                        if (composer.text.trim().length === 0) return
                        ChatBridge.sendMessage(composer.text)
                        composer.text = ""
                    }
                }
            }
        }
    }

    Connections {
        target: ChatBridge
        function onStoreChanged() {
            messageView.model = ChatBridge.selectedMessages()
            messageView.positionViewAtEnd()
        }
    }

    Component.onCompleted: {
        messageView.model = ChatBridge.selectedMessages()
        messageView.positionViewAtEnd()
    }
}
