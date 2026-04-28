#include "app_mobile/mobile_chat_bridge.h"

#include <QMetaObject>
#include <QVariantMap>

#include <utility>

using telegram_like::client::transport::ControlPlaneClient;

namespace {

QString to_q(const std::string& s) { return QString::fromStdString(s); }
std::string to_std(const QString& s) { return s.toStdString(); }

}  // namespace

MobileChatBridge::MobileChatBridge(QObject* parent) : QObject(parent) {
    setStatus(QStringLiteral("Disconnected"));
}

MobileChatBridge::~MobileChatBridge() {
    shutting_down_ = true;
    if (client_) client_->disconnect();
}

QString MobileChatBridge::currentUserId() const {
    if (!client_) return {};
    return to_q(client_->user_id());
}

QString MobileChatBridge::currentDisplayName() const {
    return display_name_;
}

QString MobileChatBridge::selectedConversationId() const {
    return to_q(store_.selected_conversation_id());
}

bool MobileChatBridge::connected() const noexcept {
    return client_ != nullptr && client_->is_connected();
}

QString MobileChatBridge::statusText() const {
    return status_;
}

void MobileChatBridge::setStatus(const QString& s) {
    if (status_ == s) return;
    status_ = s;
    emit statusChanged();
}

void MobileChatBridge::emitStoreChanged() {
    emit storeChanged();
}

void MobileChatBridge::connectAndLogin(const QString& host, int port,
                                       const QString& user, const QString& password,
                                       const QString& device) {
    setStatus(QStringLiteral("Connecting..."));
    const auto h = to_std(host);
    const auto u = to_std(user);
    const auto pw = to_std(password);
    const auto dev = to_std(device);
    const auto port16 = static_cast<unsigned short>(port);

    std::thread([this, h, port16, u, pw, dev] {
        auto next_client = std::make_shared<ControlPlaneClient>();
        if (!next_client->connect(h, port16)) {
            QMetaObject::invokeMethod(this, [this] {
                if (shutting_down_) return;
                setStatus(QStringLiteral("Connect failed"));
                emit errorReported(QStringLiteral("connect failed"));
            }, Qt::QueuedConnection);
            return;
        }
        const auto auth = next_client->login(u, pw, dev);
        if (!auth.ok) {
            QMetaObject::invokeMethod(this, [this, code = auth.error_code, msg = auth.error_message] {
                if (shutting_down_) return;
                setStatus(QStringLiteral("Login failed"));
                emit errorReported(to_q(code + " " + msg));
            }, Qt::QueuedConnection);
            return;
        }
        next_client->set_push_handler([this](const std::string& type, const std::string& env_json) {
            QMetaObject::invokeMethod(this, [this, type, env_json] {
                if (shutting_down_) return;
                store_.apply_push(type, env_json);
                emitStoreChanged();
            }, Qt::QueuedConnection);
        });
        next_client->start_heartbeat(10000);
        const auto sync = next_client->conversation_sync();

        QMetaObject::invokeMethod(this, [this, auth, sync, client = std::move(next_client)] {
            if (shutting_down_) return;
            client_ = client;
            store_.set_current_user(auth.user_id);
            display_name_ = to_q(auth.display_name);
            if (sync.ok) store_.apply_sync(sync);
            // Auto-select the first conversation so the UI lands somewhere useful.
            const auto convs = store_.conversations();
            if (!convs.empty()) {
                store_.set_selected_conversation(convs.front().conversation_id);
            }
            setStatus(to_q(std::string("Connected as ") + auth.user_id));
            emit identityChanged();
            emit connectedChanged();
            emitStoreChanged();
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::selectChat(const QString& conversationId) {
    store_.set_selected_conversation(to_std(conversationId));
    emitStoreChanged();
}

void MobileChatBridge::sendMessage(const QString& text) {
    if (!client_ || text.trimmed().isEmpty()) return;
    const auto conv = store_.selected_conversation_id();
    if (conv.empty()) return;
    const auto body = to_std(text);
    const auto pending_id = store_.add_pending_message(conv, body);
    emitStoreChanged();
    auto client = client_;
    std::thread([this, client, conv, body, pending_id] {
        const auto sent = client->send_message(conv, body);
        QMetaObject::invokeMethod(this, [this, conv, pending_id, sent] {
            if (shutting_down_) return;
            if (!sent.ok) {
                store_.fail_pending_message(conv, pending_id, sent.error_code + " " + sent.error_message);
            } else {
                store_.resolve_pending_message(conv, pending_id, sent);
            }
            emitStoreChanged();
        }, Qt::QueuedConnection);
    }).detach();
}

QVariantList MobileChatBridge::conversationList() const {
    QVariantList out;
    for (const auto& c : store_.conversations()) {
        QVariantMap row;
        row["conversationId"] = to_q(c.conversation_id);
        row["title"] = to_q(c.title.empty() ? c.conversation_id : c.title);
        row["unread"] = static_cast<int>(c.unread_count);
        if (!c.messages.empty()) {
            const auto& last = c.messages.back();
            row["lastSnippet"] = to_q(last.text.size() > 60
                ? last.text.substr(0, 60) + "..." : last.text);
        } else {
            row["lastSnippet"] = QStringLiteral("");
        }
        out.append(row);
    }
    return out;
}

QVariantList MobileChatBridge::selectedMessages() const {
    QVariantList out;
    const auto* conv = store_.selected_conversation();
    if (conv == nullptr) return out;
    const auto self = client_ ? client_->user_id() : std::string {};
    for (const auto& m : conv->messages) {
        QVariantMap row;
        row["messageId"] = to_q(m.message_id);
        row["sender"] = to_q(m.sender_user_id);
        row["text"] = to_q(m.deleted ? std::string("<deleted>") : m.text);
        row["outgoing"] = (m.sender_user_id == self);
        row["pending"] = (m.delivery_state == "pending");
        row["failed"] = (m.delivery_state == "failed");
        row["createdAtMs"] = static_cast<qlonglong>(m.created_at_ms);
        out.append(row);
    }
    return out;
}
