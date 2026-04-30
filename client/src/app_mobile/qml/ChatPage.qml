import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: page
    // M137 / M143: pull palette from the root ApplicationWindow's Theme so
    // dark mode just works.
    readonly property var palette: ApplicationWindow.window.theme
    background: Rectangle { color: page.palette.chatArea }

    signal backRequested()

    // M143 reply state — set by the long-press "Reply" action; the composer
    // shows a quote strip above the input until the user sends or cancels.
    property string replyToId: ""
    property string replyToText: ""

    header: Rectangle {
        height: 56
        color: page.palette.primary
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

    // M141 / M143: long-press menu shared across all bubbles.
    Menu {
        id: messageMenu
        property string targetId: ""
        property bool targetOutgoing: false
        property bool targetPinned: false
        MenuItem { text: qsTr("Reply"); onTriggered: {
            page.replyToId = messageMenu.targetId
            page.replyToText = messageMenu.targetText
            composer.forceActiveFocus()
        } }
        MenuItem { text: qsTr("Forward (same chat)"); onTriggered: {
            ChatBridge.forwardMessage(messageMenu.targetId, "")
        } }
        MenuItem { text: qsTr("React 👍"); onTriggered: {
            ChatBridge.toggleReaction(messageMenu.targetId, "+1")
        } }
        MenuItem { text: qsTr("React ❤"); onTriggered: {
            ChatBridge.toggleReaction(messageMenu.targetId, "heart")
        } }
        MenuSeparator {}
        MenuItem {
            text: messageMenu.targetPinned ? qsTr("Unpin") : qsTr("Pin")
            onTriggered: ChatBridge.pinMessage(messageMenu.targetId, !messageMenu.targetPinned)
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("Edit")
            enabled: messageMenu.targetOutgoing
            onTriggered: editDialog.open()
        }
        MenuItem {
            text: qsTr("Delete")
            enabled: messageMenu.targetOutgoing
            onTriggered: ChatBridge.deleteMessage(messageMenu.targetId)
        }
        property string targetText: ""
    }

    Dialog {
        id: editDialog
        title: qsTr("Edit message")
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentItem: TextField {
            id: editField
            text: messageMenu.targetText
            width: 280
        }
        onAccepted: {
            if (editField.text.trim().length > 0) {
                ChatBridge.editMessage(messageMenu.targetId, editField.text)
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
                id: row
                width: messageView.width
                implicitHeight: bubble.implicitHeight + 12
                height: implicitHeight
                // M149: swipe-right-to-reply offset. Reset on press; bumped
                // by MouseArea while dragging; animates back to 0 on
                // release (whether or not the swipe completed).
                property real swipeOffset: 0
                Behavior on swipeOffset { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                // Reply hint glyph that fades in from the left as the user
                // drags — gives visual confirmation a swipe is recognised.
                Label {
                    text: "\u21A9"  // ↩ (leftwards arrow with hook)
                    color: page.palette.primary
                    font.pointSize: 18
                    opacity: Math.min(1, row.swipeOffset / 60)
                    anchors {
                        left: parent.left
                        leftMargin: 8 + Math.min(row.swipeOffset, 56)
                        verticalCenter: parent.verticalCenter
                    }
                    visible: opacity > 0.05
                }
                Rectangle {
                    id: bubble
                    radius: 14
                    gradient: modelData.outgoing && !modelData.failed ? ownGradient : null
                    color: modelData.failed
                          ? "#ffd7cf"
                          : (modelData.outgoing ? "transparent" : page.palette.peerBubble)
                    border.color: modelData.pending ? "#b88a16" : "transparent"
                    border.width: modelData.pending ? 1 : 0
                    width: Math.min(parent.width * 0.78,
                                    Math.max(120, contentLabel.implicitWidth + 28))
                    implicitHeight: bubbleColumn.implicitHeight + 12
                    // M149: shift the bubble by swipeOffset so the user
                    // sees the gesture progress live.
                    x: row.swipeOffset * (modelData.outgoing ? -1 : 1) * 0
                    anchors {
                        right: modelData.outgoing ? parent.right : undefined
                        left: modelData.outgoing ? undefined : parent.left
                        rightMargin: 10
                        leftMargin: 10 + (modelData.outgoing ? 0 : row.swipeOffset)
                        verticalCenter: parent.verticalCenter
                    }
                    Gradient {
                        id: ownGradient
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: page.palette.ownBubbleTop }
                        GradientStop { position: 1.0; color: page.palette.ownBubbleBottom }
                    }
                    // M141 + M149: tap = focus, press-and-hold = open the
                    // long-press menu, drag-right (>50 px) = swipe-to-reply.
                    // The drag detector lives at row level so the bubble
                    // can translate live; the press-and-hold logic stays
                    // inside the bubble area for a tighter hit target.
                    MouseArea {
                        anchors.fill: parent
                        property real pressX: 0
                        property real pressY: 0
                        property bool draggingHorizontal: false
                        onPressed: function(mouse) {
                            pressX = mouse.x
                            pressY = mouse.y
                            draggingHorizontal = false
                            row.swipeOffset = 0
                        }
                        onPositionChanged: function(mouse) {
                            if (!pressed) return
                            const dx = mouse.x - pressX
                            const dy = Math.abs(mouse.y - pressY)
                            // Only commit to a horizontal drag if motion is
                            // mostly sideways — otherwise let the parent
                            // ListView keep ownership of vertical scroll.
                            if (!draggingHorizontal && dx > 12 && dx > dy * 1.5) {
                                draggingHorizontal = true
                            }
                            if (draggingHorizontal) {
                                row.swipeOffset = Math.max(0, Math.min(80, dx))
                            }
                        }
                        onReleased: {
                            if (draggingHorizontal && row.swipeOffset > 50) {
                                page.replyToId = modelData.messageId
                                page.replyToText = modelData.text || ""
                                composer.forceActiveFocus()
                            }
                            row.swipeOffset = 0
                            draggingHorizontal = false
                        }
                        onPressAndHold: {
                            // pressAndHold fires only when motion is small —
                            // a real swipe will have already set
                            // draggingHorizontal and we suppress the menu.
                            if (draggingHorizontal) return
                            messageMenu.targetId = modelData.messageId
                            messageMenu.targetOutgoing = !!modelData.outgoing
                            messageMenu.targetPinned = !!modelData.pinned
                            messageMenu.targetText = modelData.text || ""
                            messageMenu.popup()
                        }
                    }
                    ColumnLayout {
                        id: bubbleColumn
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2
                        // sender name (peer side, useful in groups)
                        Label {
                            visible: !modelData.outgoing && (modelData.sender || "") !== ""
                            text: modelData.sender
                            color: page.palette.primary
                            font.pointSize: 9
                            font.bold: true
                        }
                        // M143 forwarded header (italic)
                        Label {
                            visible: (modelData.forwardedFrom || "") !== ""
                            text: qsTr("Forwarded from %1").arg(modelData.forwardedFrom || "")
                            color: modelData.outgoing && !modelData.failed
                                ? "#e6f1ff"
                                : page.palette.textMuted
                            font.italic: true
                            font.pointSize: 9
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                        }
                        // M143 reply quote (vertical accent bar + 1-line snippet)
                        RowLayout {
                            visible: (modelData.replyTo || "") !== ""
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                color: modelData.outgoing && !modelData.failed
                                    ? "#cee9ff"
                                    : page.palette.primary
                                Layout.preferredWidth: 3
                                Layout.preferredHeight: 26
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label {
                                    text: qsTr("Reply: %1").arg(modelData.replyTo || "")
                                    color: modelData.outgoing && !modelData.failed
                                        ? "#cee9ff"
                                        : page.palette.primary
                                    font.bold: true
                                    font.pointSize: 9
                                }
                                Label {
                                    text: (modelData.replyToText || "").substring(0, 80)
                                    color: modelData.outgoing && !modelData.failed
                                        ? "#e6f1ff"
                                        : page.palette.textMuted
                                    font.pointSize: 9
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }
                        // M143 pinned tag
                        Label {
                            visible: !!modelData.pinned
                            text: "\uD83D\uDCCC " + qsTr("pinned")  // 📌
                            color: modelData.outgoing && !modelData.failed
                                ? "#e6f1ff"
                                : page.palette.textMuted
                            font.pointSize: 8
                        }
                        // body text + edited suffix
                        Label {
                            id: contentLabel
                            text: (modelData.text || "")
                                + (modelData.edited ? "  " + qsTr("(edited)") : "")
                            color: modelData.outgoing && !modelData.failed
                                ? page.palette.ownBubbleText
                                : page.palette.peerBubbleText
                            font.pointSize: 12
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        // M143 reactions chips row
                        Flow {
                            visible: (modelData.reactions || "") !== ""
                            Layout.fillWidth: true
                            spacing: 4
                            Repeater {
                                model: (modelData.reactions || "").split(",").filter(function(s) { return s.length > 0 })
                                delegate: Rectangle {
                                    radius: 9
                                    color: modelData.outgoing && !modelData.failed
                                        ? Qt.rgba(1, 1, 1, 0.22)
                                        : Qt.lighter(page.palette.textMuted, 1.8)
                                    implicitWidth: chipText.implicitWidth + 14
                                    implicitHeight: 18
                                    Label {
                                        id: chipText
                                        anchors.centerIn: parent
                                        text: {
                                            const colon = modelData.indexOf(":")
                                            return colon > 0
                                                ? modelData.substring(0, colon) + " " + modelData.substring(colon + 1)
                                                : modelData
                                        }
                                        color: modelData.outgoing && !modelData.failed
                                            ? "#ffffff"
                                            : page.palette.peerBubbleText
                                        font.pointSize: 9
                                    }
                                }
                            }
                        }
                        // M137 tick row at bottom-right of own bubbles
                        RowLayout {
                            visible: modelData.outgoing
                            Layout.alignment: Qt.AlignRight
                            spacing: 4
                            Label {
                                text: {
                                    if (modelData.pending) return "\u231b";
                                    if (modelData.failed)  return "\u2715";
                                    if (modelData.deliveryTick === "read") return "\u2713\u2713";
                                    return "\u2713";
                                }
                                color: modelData.failed
                                    ? "#9b3412"
                                    : (modelData.deliveryTick === "read" ? "#ffffff" : "#cee9ff")
                                font.pointSize: 10
                                font.letterSpacing: -1
                            }
                        }
                    }
                }
            }
        }

        // M143 reply quote strip ABOVE the composer when replyToId is set.
        Rectangle {
            visible: page.replyToId !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: page.palette.surfaceMuted
            border.color: page.palette.border
            border.width: 0
            RowLayout {
                anchors.fill: parent
                anchors.margins: 6
                Rectangle {
                    color: page.palette.primary
                    Layout.preferredWidth: 3
                    Layout.preferredHeight: 24
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label {
                        text: qsTr("Replying to %1").arg(page.replyToId)
                        color: page.palette.primary
                        font.bold: true
                        font.pointSize: 9
                    }
                    Label {
                        text: page.replyToText.substring(0, 60)
                        color: page.palette.textMuted
                        font.pointSize: 9
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                Button {
                    text: "✕"
                    flat: true
                    onClicked: { page.replyToId = ""; page.replyToText = "" }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: page.palette.surface
            border.color: page.palette.border
            border.width: 0
            Rectangle {
                anchors { top: parent.top; left: parent.left; right: parent.right }
                height: 1
                color: page.palette.border
            }
            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                TextField {
                    id: composer
                    Layout.fillWidth: true
                    placeholderText: qsTr("Message")
                    color: page.palette.textPrimary
                    Keys.onReturnPressed: sendButton.clicked()
                    background: Rectangle {
                        radius: 18
                        color: page.palette.surfaceMuted
                        border.color: composer.activeFocus ? page.palette.primary : page.palette.border
                        border.width: 1
                    }
                }
                Button {
                    id: sendButton
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    background: Rectangle {
                        radius: 22
                        color: sendButton.down ? page.palette.primaryHover : page.palette.primary
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
                        // M143: when there's an active reply target, route through
                        // replyMessage so the new message carries reply_to_message_id.
                        if (page.replyToId !== "") {
                            ChatBridge.replyMessage(page.replyToId, composer.text)
                            page.replyToId = ""
                            page.replyToText = ""
                        } else {
                            ChatBridge.sendMessage(composer.text)
                        }
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
