#pragma once

#include "app_desktop/desktop_chat_store.h"
#include "transport/control_plane_client.h"

#include <QAbstractListModel>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <QtQml/qqml.h>

#include <atomic>
#include <memory>
#include <thread>

// Thin QML-facing facade over ControlPlaneClient + DesktopChatStore.
// In the global namespace so qt_add_qml_module's auto-generated type
// registration code can resolve the QML_ELEMENT without a using-declaration.
//
// QML invokes connect()/sendMessage()/selectChat() through Q_INVOKABLE; the
// bridge fans state changes back via signals so QML's ListView/Repeater can
// re-bind. Threading: every RPC happens on a detached worker thread and
// marshals the result back via QMetaObject::invokeMethod (same shape as the
// Qt Widgets desktop app).
class MobileChatBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString currentUserId READ currentUserId NOTIFY identityChanged)
    Q_PROPERTY(QString currentDisplayName READ currentDisplayName NOTIFY identityChanged)
    Q_PROPERTY(QString selectedConversationId READ selectedConversationId NOTIFY storeChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusChanged)
    QML_ELEMENT

public:
    explicit MobileChatBridge(QObject* parent = nullptr);
    ~MobileChatBridge() override;

    [[nodiscard]] QString currentUserId() const;
    [[nodiscard]] QString currentDisplayName() const;
    [[nodiscard]] QString selectedConversationId() const;
    [[nodiscard]] bool connected() const noexcept;
    [[nodiscard]] QString statusText() const;

    Q_INVOKABLE void connectAndLogin(const QString& host, int port,
                                     const QString& user, const QString& password,
                                     const QString& device);
    Q_INVOKABLE void selectChat(const QString& conversationId);
    Q_INVOKABLE void sendMessage(const QString& text);
    Q_INVOKABLE QVariantList conversationList() const;
    Q_INVOKABLE QVariantList selectedMessages() const;

    // M143: mobile parity with desktop's message-action context menu.
    // Each method dispatches the existing transport RPC on a worker
    // thread and re-emits storeChanged so QML re-pulls selectedMessages.
    Q_INVOKABLE void replyMessage(const QString& targetMessageId, const QString& text);
    Q_INVOKABLE void forwardMessage(const QString& sourceMessageId,
                                    const QString& destinationConversationId);
    Q_INVOKABLE void toggleReaction(const QString& messageId, const QString& emoji);
    Q_INVOKABLE void pinMessage(const QString& messageId, bool pinned);
    Q_INVOKABLE void editMessage(const QString& messageId, const QString& newText);
    Q_INVOKABLE void deleteMessage(const QString& messageId);

    // M120: profile + contacts + devices RPCs (Q_INVOKABLE; results arrive
    // via the corresponding *Ready signals so QML can rebind ListView models).
    Q_INVOKABLE void refreshProfile();
    Q_INVOKABLE void saveProfile(const QString& displayName);
    Q_INVOKABLE void refreshContacts();
    Q_INVOKABLE void addContact(const QString& userId);
    Q_INVOKABLE void removeContact(const QString& userId);
    Q_INVOKABLE void searchUsers(const QString& query);
    Q_INVOKABLE void refreshDevices();
    Q_INVOKABLE void revokeDevice(const QString& deviceId);
    Q_INVOKABLE void updateDeviceTrust(const QString& deviceId, bool trusted);

    // M121: server message search + remote-control + attachments
    Q_INVOKABLE void searchMessages(const QString& query);
    Q_INVOKABLE void remoteInvite(const QString& targetDevice);
    Q_INVOKABLE void remoteApprove(const QString& remoteSessionId);
    Q_INVOKABLE void remoteTerminate(const QString& remoteSessionId);
    Q_INVOKABLE void remoteRendezvous(const QString& remoteSessionId);
    Q_INVOKABLE QVariantList selectedAttachments() const;
    Q_INVOKABLE void fetchAttachment(const QString& attachmentId);

    // M122: voice/video calls
    Q_INVOKABLE void callInvite(const QString& calleeUserId,
                                const QString& calleeDeviceId,
                                const QString& kind);
    Q_INVOKABLE void callAccept(const QString& callId);
    Q_INVOKABLE void callDecline(const QString& callId);
    Q_INVOKABLE void callEnd(const QString& callId);

signals:
    void connectedChanged();
    void identityChanged();
    void storeChanged();
    void statusChanged();
    void errorReported(const QString& detail);
    // M120 result signals.
    void profileReady(const QVariantMap& profile);
    void contactsReady(const QVariantList& contacts);
    void searchUsersReady(const QVariantList& users);
    void devicesReady(const QVariantList& devices);
    // M121
    void searchMessagesReady(const QVariantList& matches);
    void remoteResult(const QString& kind, bool ok, const QVariantMap& payload);
    void attachmentReady(const QString& attachmentId, const QString& filename,
                         const QString& mimeType, qlonglong sizeBytes);
    // M122
    void callStateChanged(const QVariantMap& callState);

private:
    void setStatus(const QString& s);
    void emitStoreChanged();

    std::shared_ptr<telegram_like::client::transport::ControlPlaneClient> client_;
    telegram_like::client::app_desktop::DesktopChatStore store_;
    QString status_;
    QString display_name_;
    QString device_id_;
    std::atomic<bool> shutting_down_ {false};
};
