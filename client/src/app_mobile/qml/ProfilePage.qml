import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M120: view + edit current user's display name.
Page {
    id: page
    background: Rectangle { color: "#f4f5f7" }

    signal backRequested()

    property var profile: ({ userId: "", username: "", displayName: "" })
    property var accountFeatures: ({ storiesCount: 0, emojiStatus: "", lastStoryTitle: "", lastGiftTitle: "" })

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
                text: qsTr("Profile"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
        }
    }

    Connections {
        target: ChatBridge
        function onProfileReady(p) {
            page.profile = p
            displayField.text = p.displayName
        }
        function onAccountFeaturesReady(features) {
            page.accountFeatures = features
            emojiField.text = features.emojiStatus || ""
        }
    }

    Component.onCompleted: {
        ChatBridge.refreshProfile()
        ChatBridge.refreshAccountFeatures()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18; spacing: 12

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 96; height: 96; radius: 48; color: "#3390ec"
            Label {
                anchors.centerIn: parent
                text: (page.profile.displayName || page.profile.userId || "?").substring(0, 1).toUpperCase()
                color: "white"; font.bold: true; font.pointSize: 36
            }
        }

        Label {
            text: qsTr("USER ID"); font.bold: true; font.pointSize: 9; color: "#7c8a96"
        }
        Label {
            text: page.profile.userId; color: "#0f1419"; font.pointSize: 12
        }

        Label {
            text: qsTr("USERNAME"); font.bold: true; font.pointSize: 9; color: "#7c8a96"
        }
        Label {
            text: page.profile.username; color: "#0f1419"; font.pointSize: 12
        }

        Label {
            text: qsTr("DISPLAY NAME"); font.bold: true; font.pointSize: 9; color: "#7c8a96"
        }
        TextField {
            id: displayField
            Layout.fillWidth: true
            placeholderText: qsTr("How others see you")
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Button {
                text: qsTr("Save"); enabled: displayField.text.trim().length > 0
                Layout.fillWidth: true
                onClicked: ChatBridge.saveProfile(displayField.text.trim())
            }
            Button {
                text: qsTr("Reload")
                onClicked: ChatBridge.refreshProfile()
            }
        }
        Rectangle {
            Layout.fillWidth: true
            radius: 10
            color: "white"
            implicitHeight: accountFeatureBox.implicitHeight + 24
            ColumnLayout {
                id: accountFeatureBox
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8
                Label { text: qsTr("Stories and gifts"); font.bold: true; color: "#0f1419" }
                Label {
                    text: qsTr("Stories: %1 · Last story: %2 · Last gift: %3")
                        .arg(page.accountFeatures.storiesCount)
                        .arg(page.accountFeatures.lastStoryTitle || qsTr("none"))
                        .arg(page.accountFeatures.lastGiftTitle || qsTr("none"))
                    color: "#56616b"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: emojiField; Layout.fillWidth: true; placeholderText: qsTr("Emoji status") }
                    Button { text: qsTr("Set"); onClicked: ChatBridge.setEmojiStatus(emojiField.text.trim()) }
                }
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: storyTitleField; Layout.fillWidth: true; placeholderText: qsTr("Story title") }
                    Button { text: qsTr("Publish"); onClicked: ChatBridge.publishStory(storyTitleField.text.trim(), qsTr("Published from mobile")) }
                }
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: giftRecipientField; Layout.fillWidth: true; placeholderText: qsTr("Gift recipient user_id") }
                    Button { text: qsTr("Gift"); onClicked: ChatBridge.sendGift(qsTr("Mobile Gift"), giftRecipientField.text.trim()) }
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
