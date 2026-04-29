import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M121: invoke remote-control RPCs (invite/approve/terminate/rendezvous)
// against the connected control plane and surface the typed result.
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
                text: qsTr("Remote control"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
        }
    }

    Connections {
        target: ChatBridge
        function onRemoteResult(kind, ok, payload) {
            if (kind === "invite" && ok && payload.remoteSessionId) {
                rsField.text = payload.remoteSessionId
            }
            const tag = ok ? "[ok]" : "[err " + (payload.errorCode || "?") + "]"
            log.appendPlainText(tag + " " + kind + ": " + JSON.stringify(payload))
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12; spacing: 10

        Label {
            text: qsTr("Invite a target device")
            color: "#7c8a96"; font.bold: true; font.pointSize: 9
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            TextField {
                id: targetField
                Layout.fillWidth: true
                placeholderText: qsTr("target device_id (e.g. dev_bob_win)")
            }
            Button {
                text: qsTr("Invite"); enabled: targetField.text.trim().length > 0
                onClicked: ChatBridge.remoteInvite(targetField.text.trim())
            }
        }

        Label {
            text: qsTr("remote_session_id")
            color: "#7c8a96"; font.bold: true; font.pointSize: 9
        }
        TextField {
            id: rsField
            Layout.fillWidth: true
            placeholderText: qsTr("from invite or push")
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            Button {
                text: qsTr("Approve"); Layout.fillWidth: true
                onClicked: ChatBridge.remoteApprove(rsField.text.trim())
            }
            Button {
                text: qsTr("Terminate"); Layout.fillWidth: true
                onClicked: ChatBridge.remoteTerminate(rsField.text.trim())
            }
            Button {
                text: qsTr("Rendezvous"); Layout.fillWidth: true
                onClicked: ChatBridge.remoteRendezvous(rsField.text.trim())
            }
        }

        Label {
            text: qsTr("RPC log")
            color: "#7c8a96"; font.bold: true; font.pointSize: 9
        }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true
            TextArea {
                id: log
                readOnly: true
                wrapMode: TextArea.WrapAnywhere
                placeholderText: qsTr("Results from remote_invite / approve / terminate / rendezvous appear here.")
            }
        }
    }
}
