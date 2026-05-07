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

    property var accountSettings: ({
        notificationsEnabled: true,
        messagePreviewEnabled: true,
        whoCanAddToGroups: "everybody",
        phoneNumberVisibility: "contacts",
        twoStepVerificationEnabled: false,
        passcodeLockEnabled: false,
        proxyMode: "system",
        proxyHost: "",
        proxyPort: 0,
        proxySecret: ""
    })
    property var accountFeatures: ({
        premium: false,
        starsBalance: 0,
        walletBalance: 0,
        giftsAvailable: 0,
        storiesCount: 0,
        emojiStatus: ""
    })

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

    Connections {
        target: ChatBridge
        function onAccountSettingsReady(settings) { page.accountSettings = settings }
        function onAccountFeaturesReady(features) { page.accountFeatures = features }
    }

    Component.onCompleted: {
        ChatBridge.refreshAccountSettings()
        ChatBridge.refreshAccountFeatures()
    }

    Flickable {
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: rootColumn.implicitHeight + 20

        ColumnLayout {
            id: rootColumn
            width: parent.width
            spacing: 10

            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: 392
                interactive: false
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
                    width: ListView.view.width
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

            Rectangle {
                Layout.fillWidth: true
                Layout.margins: 12
                radius: 10
                color: "white"
                implicitHeight: accountBox.implicitHeight + 24
                ColumnLayout {
                    id: accountBox
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    Label { text: qsTr("Telegram account settings"); font.bold: true; color: "#0f1419" }
                    CheckBox { id: notificationsToggle; text: qsTr("Notifications"); checked: page.accountSettings.notificationsEnabled }
                    CheckBox { id: previewToggle; text: qsTr("Message preview"); checked: page.accountSettings.messagePreviewEnabled }
                    CheckBox { id: twoStepToggle; text: qsTr("Two-step verification"); checked: page.accountSettings.twoStepVerificationEnabled }
                    CheckBox { id: passcodeToggle; text: qsTr("Passcode lock"); checked: page.accountSettings.passcodeLockEnabled }
                    ComboBox { id: groupsCombo; Layout.fillWidth: true; model: ["everybody", "contacts", "nobody"]; currentIndex: Math.max(0, model.indexOf(page.accountSettings.whoCanAddToGroups)) }
                    ComboBox { id: phoneCombo; Layout.fillWidth: true; model: ["everybody", "contacts", "nobody"]; currentIndex: Math.max(0, model.indexOf(page.accountSettings.phoneNumberVisibility)) }
                    RowLayout {
                        Layout.fillWidth: true
                        ComboBox { id: proxyModeCombo; Layout.preferredWidth: 116; model: ["system", "disabled", "socks5", "mtproto"]; currentIndex: Math.max(0, model.indexOf(page.accountSettings.proxyMode)) }
                        TextField { id: proxyHostField; Layout.fillWidth: true; text: page.accountSettings.proxyHost; placeholderText: qsTr("Proxy host") }
                        TextField { id: proxyPortField; Layout.preferredWidth: 82; text: page.accountSettings.proxyPort > 0 ? String(page.accountSettings.proxyPort) : ""; placeholderText: qsTr("Port"); inputMethodHints: Qt.ImhDigitsOnly }
                    }
                    TextField { id: proxySecretField; Layout.fillWidth: true; text: page.accountSettings.proxySecret; placeholderText: qsTr("Proxy secret") }
                    Button {
                        text: qsTr("Save settings")
                        Layout.fillWidth: true
                        onClicked: ChatBridge.saveAccountSettings(
                            notificationsToggle.checked,
                            previewToggle.checked,
                            groupsCombo.currentText,
                            phoneCombo.currentText,
                            twoStepToggle.checked,
                            passcodeToggle.checked,
                            proxyModeCombo.currentText,
                            proxyHostField.text.trim(),
                            parseInt(proxyPortField.text || "0"),
                            proxySecretField.text)
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.margins: 12
                radius: 10
                color: "white"
                implicitHeight: featureBox.implicitHeight + 24
                ColumnLayout {
                    id: featureBox
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8
                    Label { text: qsTr("Premium / Wallet / Stories"); font.bold: true; color: "#0f1419" }
                    Label {
                        text: qsTr("Premium: %1 · Stars: %2 · Wallet: %3 · Gifts: %4 · Stories: %5")
                            .arg(page.accountFeatures.premium ? qsTr("active") : qsTr("inactive"))
                            .arg(page.accountFeatures.starsBalance)
                            .arg(page.accountFeatures.walletBalance)
                            .arg(page.accountFeatures.giftsAvailable)
                            .arg(page.accountFeatures.storiesCount)
                        color: "#56616b"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: emojiStatusField; Layout.fillWidth: true; text: page.accountFeatures.emojiStatus; placeholderText: qsTr("Emoji status") }
                        Button { text: qsTr("Save"); onClicked: ChatBridge.setEmojiStatus(emojiStatusField.text.trim()) }
                    }
                    Button { text: qsTr("Refresh account features"); Layout.fillWidth: true; onClicked: ChatBridge.refreshAccountFeatures() }
                }
            }
        }
    }
}
