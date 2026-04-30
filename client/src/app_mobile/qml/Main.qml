import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 380
    height: 720
    visible: true
    title: qsTr("Telegram-like")

    // M136: theme tokens live in Theme.qml so the desktop and mobile UIs
    // share one palette spec. Toggling root.theme.darkMode flips every
    // child page in one place. The legacy `appBackground / accentBlue / …`
    // properties are kept as aliases pointing at the active palette so
    // pages that haven't migrated yet still resolve.
    readonly property Theme theme: Theme {
        // `themeDarkMode` is a context property pushed by app_mobile/main.cpp
        // after reading the TELEGRAM_LIKE_THEME env var (same contract as
        // the desktop client). When the binary is loaded from a runtime
        // that hasn't set the property (e.g. qmllint, designer preview) the
        // typeof guard keeps QML from crashing on the missing identifier.
        darkMode: typeof themeDarkMode !== "undefined" ? !!themeDarkMode : false
    }
    readonly property color appBackground:      theme.appBackground
    readonly property color chatAreaBackground: theme.chatArea
    readonly property color sidebarBackground:  theme.surface
    readonly property color accentBlue:         theme.primary
    readonly property color outgoingBubble:     theme.ownBubbleBottom
    readonly property color incomingBubble:     theme.peerBubble
    readonly property color subtleText:         theme.textMuted
    readonly property color primaryText:        theme.textPrimary

    color: theme.appBackground

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
