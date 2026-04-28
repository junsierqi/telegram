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

signals:
    void connectedChanged();
    void identityChanged();
    void storeChanged();
    void statusChanged();
    void errorReported(const QString& detail);

private:
    void setStatus(const QString& s);
    void emitStoreChanged();

    std::shared_ptr<telegram_like::client::transport::ControlPlaneClient> client_;
    telegram_like::client::app_desktop::DesktopChatStore store_;
    QString status_;
    QString display_name_;
    std::atomic<bool> shutting_down_ {false};
};
