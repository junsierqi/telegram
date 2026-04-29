import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// M122: voice/video call control. invite/accept/decline/end map directly to
// CallSessionService FSM (ringing -> accepted/declined/canceled/ended).
Page {
    id: page
    background: Rectangle { color: "#f4f5f7" }

    signal backRequested()

    property string activeCallId: ""
    property string activeState: ""

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
                text: qsTr("Call"); color: "white"; font.bold: true
                font.pointSize: 14; Layout.fillWidth: true
            }
        }
    }

    Connections {
        target: ChatBridge
        function onCallStateChanged(state) {
            if (state.errorCode) {
                log.appendPlainText("[err " + state.errorCode + "] " + (state.errorMessage || ""))
                return
            }
            page.activeCallId = state.callId
            page.activeState = state.state
            log.appendPlainText("[" + state.state + "] " + state.callId
                                + (state.kind ? " · " + state.kind : ""))
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12; spacing: 10

        // ---- start a call ----
        Label {
            text: qsTr("Start a call"); color: "#7c8a96"; font.bold: true; font.pointSize: 9
        }
        TextField {
            id: calleeUserField
            Layout.fillWidth: true
            placeholderText: qsTr("callee user_id (e.g. u_bob)")
        }
        TextField {
            id: calleeDeviceField
            Layout.fillWidth: true
            placeholderText: qsTr("callee device_id (optional)")
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            ComboBox {
                id: kindCombo
                model: ["audio", "video"]
                currentIndex: 0
            }
            Button {
                text: qsTr("Invite")
                Layout.fillWidth: true
                enabled: calleeUserField.text.trim().length > 0
                onClicked: ChatBridge.callInvite(
                    calleeUserField.text.trim(),
                    calleeDeviceField.text.trim(),
                    kindCombo.currentText)
            }
        }

        // ---- active call controls ----
        Rectangle {
            Layout.fillWidth: true; height: 1; color: "#eef0f2"
        }
        Label {
            text: qsTr("Active call: ") + (page.activeCallId || "—")
                  + (page.activeState ? " · " + page.activeState : "")
            color: "#0f1419"; font.bold: true
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            Button {
                text: qsTr("Accept"); Layout.fillWidth: true
                enabled: page.activeCallId.length > 0 && page.activeState === "ringing"
                onClicked: ChatBridge.callAccept(page.activeCallId)
            }
            Button {
                text: qsTr("Decline"); Layout.fillWidth: true
                enabled: page.activeCallId.length > 0 && page.activeState === "ringing"
                onClicked: ChatBridge.callDecline(page.activeCallId)
            }
            Button {
                text: qsTr("End"); Layout.fillWidth: true
                enabled: page.activeCallId.length > 0
                         && page.activeState !== "ended"
                         && page.activeState !== "declined"
                         && page.activeState !== "canceled"
                onClicked: ChatBridge.callEnd(page.activeCallId)
            }
        }

        Label {
            text: qsTr("FSM log"); color: "#7c8a96"; font.bold: true; font.pointSize: 9
        }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true
            TextArea {
                id: log
                readOnly: true
                placeholderText: qsTr("State transitions appear here.")
                wrapMode: TextArea.WrapAnywhere
            }
        }
    }
}
