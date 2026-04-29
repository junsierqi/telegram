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

        QMetaObject::invokeMethod(this, [this, auth, sync, dev, client = std::move(next_client)] {
            if (shutting_down_) return;
            client_ = client;
            store_.set_current_user(auth.user_id);
            display_name_ = to_q(auth.display_name);
            device_id_ = to_q(dev);
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

// ---- M120: profile / contacts / devices ----

namespace {
template <typename Result>
QVariantMap remote_error(const Result& r) {
    QVariantMap m;
    m["error_code"] = to_q(r.error_code);
    m["error_message"] = to_q(r.error_message);
    return m;
}
}  // namespace

void MobileChatBridge::refreshProfile() {
    if (!client_) return;
    auto client = client_;
    std::thread([this, client] {
        const auto r = client->profile_get();
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("profile " + r.error_code + " " + r.error_message)); return; }
            QVariantMap p;
            p["userId"] = to_q(r.user_id);
            p["username"] = to_q(r.username);
            p["displayName"] = to_q(r.display_name);
            display_name_ = to_q(r.display_name);
            emit identityChanged();
            emit profileReady(p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::saveProfile(const QString& displayName) {
    if (!client_) return;
    const auto name = to_std(displayName);
    auto client = client_;
    std::thread([this, client, name] {
        const auto r = client->profile_update(name);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("save_profile " + r.error_code + " " + r.error_message)); return; }
            QVariantMap p;
            p["userId"] = to_q(r.user_id);
            p["username"] = to_q(r.username);
            p["displayName"] = to_q(r.display_name);
            display_name_ = to_q(r.display_name);
            emit identityChanged();
            emit profileReady(p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::refreshContacts() {
    if (!client_) return;
    auto client = client_;
    std::thread([this, client] {
        const auto r = client->list_contacts();
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("contacts " + r.error_code + " " + r.error_message)); return; }
            QVariantList out;
            for (const auto& c : r.contacts) {
                QVariantMap row;
                row["userId"] = to_q(c.user_id);
                row["displayName"] = to_q(c.display_name);
                row["online"] = c.online;
                out.append(row);
            }
            emit contactsReady(out);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::addContact(const QString& userId) {
    if (!client_) return;
    const auto uid = to_std(userId);
    auto client = client_;
    std::thread([this, client, uid] {
        const auto r = client->add_contact(uid);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("contact_add " + r.error_code + " " + r.error_message)); return; }
            refreshContacts();
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::removeContact(const QString& userId) {
    if (!client_) return;
    const auto uid = to_std(userId);
    auto client = client_;
    std::thread([this, client, uid] {
        const auto r = client->remove_contact(uid);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("contact_remove " + r.error_code + " " + r.error_message)); return; }
            refreshContacts();
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::searchUsers(const QString& query) {
    if (!client_) return;
    const auto q = to_std(query);
    auto client = client_;
    std::thread([this, client, q] {
        const auto r = client->search_users(q);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("user_search " + r.error_code + " " + r.error_message)); return; }
            QVariantList out;
            for (const auto& u : r.results) {
                QVariantMap row;
                row["userId"] = to_q(u.user_id);
                row["username"] = to_q(u.username);
                row["displayName"] = to_q(u.display_name);
                row["online"] = u.online;
                row["isContact"] = u.is_contact;
                out.append(row);
            }
            emit searchUsersReady(out);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::refreshDevices() {
    if (!client_) return;
    auto client = client_;
    std::thread([this, client] {
        const auto r = client->list_devices();
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("devices " + r.error_code + " " + r.error_message)); return; }
            QVariantList out;
            for (const auto& d : r.devices) {
                QVariantMap row;
                row["deviceId"] = to_q(d.device_id);
                row["label"] = to_q(d.label);
                row["platform"] = to_q(d.platform);
                row["trusted"] = d.trusted;
                row["active"] = d.active;
                out.append(row);
            }
            emit devicesReady(out);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::revokeDevice(const QString& deviceId) {
    if (!client_) return;
    const auto did = to_std(deviceId);
    auto client = client_;
    std::thread([this, client, did] {
        const auto r = client->revoke_device(did);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("revoke " + r.error_code + " " + r.error_message)); return; }
            refreshDevices();
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::updateDeviceTrust(const QString& deviceId, bool trusted) {
    if (!client_) return;
    const auto did = to_std(deviceId);
    auto client = client_;
    std::thread([this, client, did, trusted] {
        const auto r = client->update_device_trust(did, trusted);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("trust " + r.error_code + " " + r.error_message)); return; }
            refreshDevices();
        }, Qt::QueuedConnection);
    }).detach();
}

// ---- M121: server message search / remote-control / attachments ----

void MobileChatBridge::searchMessages(const QString& query) {
    if (!client_) return;
    const auto conv = store_.selected_conversation_id();
    if (conv.empty()) return;
    const auto q = to_std(query);
    auto client = client_;
    std::thread([this, client, conv, q] {
        const auto r = client->search_messages(q, conv);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("search " + r.error_code + " " + r.error_message)); return; }
            QVariantList out;
            for (const auto& m : r.results) {
                QVariantMap row;
                row["messageId"] = to_q(m.message_id);
                row["snippet"] = to_q(m.snippet.empty() ? m.text : m.snippet);
                row["sender"] = to_q(m.sender_user_id);
                row["createdAtMs"] = static_cast<qlonglong>(m.created_at_ms);
                out.append(row);
            }
            emit searchMessagesReady(out);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::remoteInvite(const QString& targetDevice) {
    if (!client_) return;
    const auto requester = to_std(device_id_);
    const auto target = to_std(targetDevice);
    if (requester.empty() || target.empty()) return;
    auto client = client_;
    std::thread([this, client, requester, target] {
        const auto r = client->remote_invite(requester, target);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["remoteSessionId"] = to_q(r.remote_session_id);
            p["state"] = to_q(r.state);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit remoteResult(QStringLiteral("invite"), r.ok, p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::remoteApprove(const QString& remoteSessionId) {
    if (!client_) return;
    const auto rs = to_std(remoteSessionId);
    auto client = client_;
    std::thread([this, client, rs] {
        const auto r = client->remote_approve(rs);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["remoteSessionId"] = to_q(r.remote_session_id);
            p["state"] = to_q(r.state);
            p["relayEndpoint"] = to_q(r.relay_endpoint);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit remoteResult(QStringLiteral("approve"), r.ok, p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::remoteTerminate(const QString& remoteSessionId) {
    if (!client_) return;
    const auto rs = to_std(remoteSessionId);
    auto client = client_;
    std::thread([this, client, rs] {
        const auto r = client->remote_terminate(rs);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["remoteSessionId"] = to_q(r.remote_session_id);
            p["state"] = to_q(r.state);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit remoteResult(QStringLiteral("terminate"), r.ok, p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::remoteRendezvous(const QString& remoteSessionId) {
    if (!client_) return;
    const auto rs = to_std(remoteSessionId);
    auto client = client_;
    std::thread([this, client, rs] {
        const auto r = client->remote_rendezvous_request(rs);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["remoteSessionId"] = to_q(r.remote_session_id);
            p["state"] = to_q(r.state);
            p["relayEndpoint"] = to_q(r.relay_endpoint);
            p["relayKeySet"] = !r.relay_key_b64.empty();
            p["candidates"] = static_cast<int>(r.candidates.size());
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit remoteResult(QStringLiteral("rendezvous"), r.ok, p);
        }, Qt::QueuedConnection);
    }).detach();
}

QVariantList MobileChatBridge::selectedAttachments() const {
    QVariantList out;
    const auto* conv = store_.selected_conversation();
    if (conv == nullptr) return out;
    for (const auto& m : conv->messages) {
        if (m.attachment_id.empty()) continue;
        QVariantMap row;
        row["attachmentId"] = to_q(m.attachment_id);
        row["filename"] = to_q(m.filename);
        row["mimeType"] = to_q(m.mime_type);
        row["sizeBytes"] = static_cast<qlonglong>(m.size_bytes);
        row["sender"] = to_q(m.sender_user_id);
        out.append(row);
    }
    return out;
}

void MobileChatBridge::fetchAttachment(const QString& attachmentId) {
    if (!client_) return;
    const auto aid = to_std(attachmentId);
    auto client = client_;
    std::thread([this, client, aid] {
        const auto r = client->fetch_attachment(aid);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            if (!r.ok) { emit errorReported(to_q("fetch " + r.error_code + " " + r.error_message)); return; }
            emit attachmentReady(to_q(r.attachment_id), to_q(r.filename),
                                 to_q(r.mime_type), static_cast<qlonglong>(r.size_bytes));
        }, Qt::QueuedConnection);
    }).detach();
}

// ---- M122: voice/video calls ----

void MobileChatBridge::callInvite(const QString& calleeUserId,
                                  const QString& calleeDeviceId,
                                  const QString& kind) {
    if (!client_) return;
    const auto u = to_std(calleeUserId);
    const auto d = to_std(calleeDeviceId);
    const auto k = to_std(kind.isEmpty() ? QStringLiteral("audio") : kind);
    auto client = client_;
    std::thread([this, client, u, d, k] {
        const auto r = client->call_invite(u, d, k);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["callId"] = to_q(r.call_id);
            p["state"] = to_q(r.state);
            p["kind"] = to_q(r.kind);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit callStateChanged(p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::callAccept(const QString& callId) {
    if (!client_) return;
    const auto id = to_std(callId);
    auto client = client_;
    std::thread([this, client, id] {
        const auto r = client->call_accept(id);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["callId"] = to_q(r.call_id);
            p["state"] = to_q(r.state);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit callStateChanged(p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::callDecline(const QString& callId) {
    if (!client_) return;
    const auto id = to_std(callId);
    auto client = client_;
    std::thread([this, client, id] {
        const auto r = client->call_decline(id);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["callId"] = to_q(r.call_id);
            p["state"] = to_q(r.state);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit callStateChanged(p);
        }, Qt::QueuedConnection);
    }).detach();
}

void MobileChatBridge::callEnd(const QString& callId) {
    if (!client_) return;
    const auto id = to_std(callId);
    auto client = client_;
    std::thread([this, client, id] {
        const auto r = client->call_end(id);
        QMetaObject::invokeMethod(this, [this, r] {
            if (shutting_down_) return;
            QVariantMap p;
            p["callId"] = to_q(r.call_id);
            p["state"] = to_q(r.state);
            if (!r.ok) { p["errorCode"] = to_q(r.error_code); p["errorMessage"] = to_q(r.error_message); }
            emit callStateChanged(p);
        }, Qt::QueuedConnection);
    }).detach();
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
