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
            onSettingsRequested: nav.push(settingsComponent)
        }
    }

    Component {
        id: chatPageComponent
        ChatPage {
            onBackRequested: nav.pop()
        }
    }

    // M120-M122: settings hub + 7 sub-pages.
    Component {
        id: settingsComponent
        SettingsPage {
            onBackRequested: nav.pop()
            onOpenProfile:     nav.push(profileComponent)
            onOpenContacts:    nav.push(contactsComponent)
            onOpenDevices:     nav.push(devicesComponent)
            onOpenSearch:      nav.push(searchComponent)
            onOpenAttachments: nav.push(attachmentsComponent)
            onOpenRemote:      nav.push(remoteComponent)
            onOpenCall:        nav.push(callComponent)
        }
    }
    Component { id: profileComponent;     ProfilePage     { onBackRequested: nav.pop() } }
    Component { id: contactsComponent;    ContactsPage    { onBackRequested: nav.pop() } }
    Component { id: devicesComponent;     DevicesPage     { onBackRequested: nav.pop() } }
    Component { id: searchComponent;      SearchPage      { onBackRequested: nav.pop() } }
    Component { id: attachmentsComponent; AttachmentsPage { onBackRequested: nav.pop() } }
    Component { id: remoteComponent;      RemoteControlPage { onBackRequested: nav.pop() } }
    Component { id: callComponent;        CallPage        { onBackRequested: nav.pop() } }

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
