import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: page
    background: Rectangle { color: "#ffffff" }

    signal loginRequested(string host, int port, string user, string password, string device)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        Item { Layout.preferredHeight: 40 }

        // Telegram-style avatar disc placeholder for login.
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 96; height: 96; radius: 48
            color: "#3390ec"
            Label {
                anchors.centerIn: parent
                text: "✈"
                color: "white"
                font.pointSize: 36
                font.bold: true
            }
        }

        Label {
            text: qsTr("Telegram-like")
            font.pointSize: 22
            font.bold: true
            color: "#0f1419"
            Layout.alignment: Qt.AlignHCenter
        }
        Label {
            text: qsTr("Sign in to your server")
            font.pointSize: 11
            color: "#7c8a96"
            Layout.alignment: Qt.AlignHCenter
        }

        Item { Layout.preferredHeight: 8 }

        Label { text: qsTr("HOST"); font.bold: true; font.pointSize: 9; color: "#7c8a96" }
        TextField {
            id: hostField
            text: "127.0.0.1"
            Layout.fillWidth: true
            placeholderText: qsTr("e.g. 127.0.0.1")
        }

        Label { text: qsTr("PORT"); font.bold: true; font.pointSize: 9; color: "#7c8a96" }
        TextField {
            id: portField
            text: "8787"
            Layout.fillWidth: true
            inputMethodHints: Qt.ImhDigitsOnly
            validator: IntValidator { bottom: 1; top: 65535 }
        }

        Label { text: qsTr("USERNAME"); font.bold: true; font.pointSize: 9; color: "#7c8a96" }
        TextField {
            id: userField
            text: "alice"
            Layout.fillWidth: true
        }

        Label { text: qsTr("PASSWORD"); font.bold: true; font.pointSize: 9; color: "#7c8a96" }
        TextField {
            id: passwordField
            text: "alice_pw"
            Layout.fillWidth: true
            echoMode: TextInput.Password
        }

        Label { text: qsTr("DEVICE"); font.bold: true; font.pointSize: 9; color: "#7c8a96" }
        TextField {
            id: deviceField
            text: "dev_alice_mobile"
            Layout.fillWidth: true
        }

        Item { Layout.preferredHeight: 8 }

        Button {
            id: loginBtn
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            background: Rectangle {
                radius: 10
                color: loginBtn.down ? "#2079d2" : "#3390ec"
            }
            contentItem: Label {
                text: qsTr("Connect")
                color: "white"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.bold: true
                font.pointSize: 12
            }
            onClicked: page.loginRequested(
                hostField.text,
                parseInt(portField.text || "0", 10),
                userField.text,
                passwordField.text,
                deviceField.text
            )
        }

        Label {
            text: ChatBridge.statusText
            color: "#7c8a96"
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            font.pointSize: 10
        }

        Item { Layout.fillHeight: true }
    }
}
