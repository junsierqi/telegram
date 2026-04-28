import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 380
    height: 720
    visible: true
    title: qsTr("Telegram-like")

    // Minimal Telegram-style palette (light theme).
    readonly property color appBackground: "#f4f5f7"
    readonly property color chatAreaBackground: "#e6ebee"
    readonly property color sidebarBackground: "#ffffff"
    readonly property color accentBlue: "#3390ec"
    readonly property color outgoingBubble: "#eeffde"
    readonly property color incomingBubble: "#ffffff"
    readonly property color subtleText: "#7c8a96"
    readonly property color primaryText: "#0f1419"

    color: appBackground

    StackView {
        id: nav
        anchors.fill: parent
        initialItem: loginPageComponent
    }

    Component {
        id: loginPageComponent
        LoginPage {
            onLoginRequested: function(host, port, user, password, device) {
                ChatBridge.connectAndLogin(host, port, user, password, device)
            }
        }
    }

    Component {
        id: chatListComponent
        ChatListPage {
            onConversationSelected: function(conversationId) {
                ChatBridge.selectChat(conversationId)
                nav.push(chatPageComponent)
            }
        }
    }

    Component {
        id: chatPageComponent
        ChatPage {
            onBackRequested: nav.pop()
        }
    }

    Connections {
        target: ChatBridge
        function onConnectedChanged() {
            if (ChatBridge.connected && nav.depth === 1) {
                nav.push(chatListComponent)
            }
        }
        function onErrorReported(detail) {
            errorDialog.text = detail
            errorDialog.open()
        }
    }

    Dialog {
        id: errorDialog
        property string text: ""
        title: qsTr("Error")
        standardButtons: Dialog.Ok
        modal: true
        anchors.centerIn: parent
        Label {
            text: errorDialog.text
            wrapMode: Text.WordWrap
            width: 280
            color: root.primaryText
        }
    }
}
