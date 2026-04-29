import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: page
    background: Rectangle { color: "#ffffff" }

    signal conversationSelected(string conversationId)
    signal settingsRequested()

    header: Rectangle {
        height: 56
        color: "#3390ec"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 8
            Label {
                Layout.fillWidth: true
                text: ChatBridge.connected
                      ? qsTr("Chats — %1").arg(ChatBridge.currentDisplayName || ChatBridge.currentUserId)
                      : qsTr("Chats")
                color: "white"
                font.bold: true
                font.pointSize: 14
            }
            Button {
                background: Rectangle { color: "transparent" }
                contentItem: Label { text: "⚙"; color: "white"; font.pointSize: 18 }
                onClicked: page.settingsRequested()
                Layout.preferredWidth: 36
            }
        }
    }

    Connections {
        target: ChatBridge
        function onStoreChanged() { listView.model = ChatBridge.conversationList() }
        function onIdentityChanged() { listView.model = ChatBridge.conversationList() }
    }

    Component.onCompleted: listView.model = ChatBridge.conversationList()

    ListView {
        id: listView
        anchors.fill: parent
        clip: true
        spacing: 0
        delegate: Rectangle {
            width: listView.width
            height: 64
            color: tapHandler.pressed ? "#f0f3f6" : "white"
            border.color: "#eef0f2"
            border.width: 0
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: "#eef0f2"
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 22
                    // Deterministic color from the conversation id for a friendly avatar disc.
                    color: {
                        const palette = ["#e17076","#7bc862","#65aadd","#a695e7","#ee7aae","#6ec9cb","#faa774","#7d8ea0"];
                        let h = 0;
                        const s = modelData.conversationId || "";
                        for (let i = 0; i < s.length; ++i) h = (h * 31 + s.charCodeAt(i)) >>> 0;
                        return palette[h % palette.length];
                    }
                    Label {
                        anchors.centerIn: parent
                        text: (modelData.title || modelData.conversationId || "?").substring(0, 1).toUpperCase()
                        color: "white"
                        font.bold: true
                        font.pointSize: 16
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: modelData.title
                        font.bold: true
                        font.pointSize: 13
                        color: "#0f1419"
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Label {
                        text: modelData.lastSnippet
                        color: "#7c8a96"
                        font.pointSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                Rectangle {
                    visible: modelData.unread > 0
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    radius: 11
                    color: "#3390ec"
                    Label {
                        anchors.centerIn: parent
                        text: modelData.unread
                        color: "white"
                        font.bold: true
                        font.pointSize: 9
                    }
                }
            }
            TapHandler {
                id: tapHandler
                onTapped: page.conversationSelected(modelData.conversationId)
            }
        }
    }
}
