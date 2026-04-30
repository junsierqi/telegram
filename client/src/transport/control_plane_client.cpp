#include "transport/control_plane_client.h"

#include "transport/json_value.h"

#include <algorithm>
#include <chrono>
#include <sstream>

namespace telegram_like::client::transport {

namespace {

std::string json_escape(std::string_view s) {
    std::string out;
    out.reserve(s.size() + 2);
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned char>(c));
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
    return out;
}

std::string quote(std::string_view s) {
    return "\"" + json_escape(s) + "\"";
}

bool is_push_line(const std::string& line) {
    // push_ prefix check: naive scan for "correlation_id":"push_
    const std::string needle = "\"correlation_id\":\"push_";
    return line.find(needle) != std::string::npos ||
           line.find("\"correlation_id\": \"push_") != std::string::npos;
}

std::string extract_string(const JsonObject& obj, std::string_view key) {
    const auto* value = find_member(obj, key);
    if (value && value->is_string()) {
        return *value->as_string();
    }
    return {};
}

bool extract_bool(const JsonObject& obj, std::string_view key, bool fallback = false) {
    const auto* value = find_member(obj, key);
    if (!value) return fallback;
    if (auto* b = std::get_if<bool>(&value->storage)) return *b;
    return fallback;
}

long long extract_number(const JsonObject& obj, std::string_view key) {
    const auto* value = find_member(obj, key);
    if (!value) return 0;
    if (auto* d = std::get_if<double>(&value->storage)) {
        return static_cast<long long>(*d);
    }
    return 0;
}

std::string base64_encode(std::string_view bytes) {
    static constexpr char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve(((bytes.size() + 2) / 3) * 4);
    std::size_t i = 0;
    while (i + 3 <= bytes.size()) {
        const unsigned b0 = static_cast<unsigned char>(bytes[i++]);
        const unsigned b1 = static_cast<unsigned char>(bytes[i++]);
        const unsigned b2 = static_cast<unsigned char>(bytes[i++]);
        out += alphabet[(b0 >> 2) & 0x3F];
        out += alphabet[((b0 & 0x03) << 4) | (b1 >> 4)];
        out += alphabet[((b1 & 0x0F) << 2) | (b2 >> 6)];
        out += alphabet[b2 & 0x3F];
    }
    if (i < bytes.size()) {
        const unsigned b0 = static_cast<unsigned char>(bytes[i++]);
        out += alphabet[(b0 >> 2) & 0x3F];
        if (i < bytes.size()) {
            const unsigned b1 = static_cast<unsigned char>(bytes[i]);
            out += alphabet[((b0 & 0x03) << 4) | (b1 >> 4)];
            out += alphabet[(b1 & 0x0F) << 2];
            out += '=';
        } else {
            out += alphabet[(b0 & 0x03) << 4];
            out += "==";
        }
    }
    return out;
}

int base64_value(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

std::string base64_decode(std::string_view text) {
    std::string out;
    int val = 0;
    int valb = -8;
    for (char c : text) {
        if (c == '=') break;
        const int d = base64_value(c);
        if (d < 0) continue;
        val = (val << 6) + d;
        valb += 6;
        if (valb >= 0) {
            out.push_back(static_cast<char>((val >> valb) & 0xFF));
            valb -= 8;
        }
    }
    return out;
}

bool starts_with(std::string_view value, std::string_view prefix) {
    return value.size() >= prefix.size() && value.substr(0, prefix.size()) == prefix;
}

std::string text_preview(std::string_view content, std::size_t limit = 80) {
    std::string out;
    out.reserve((std::min)(content.size(), limit));
    for (const char ch : content) {
        if (out.size() >= limit) break;
        if (ch == '\r') continue;
        if (ch == '\n' || ch == '\t') {
            out.push_back(' ');
        } else if (static_cast<unsigned char>(ch) >= 0x20) {
            out.push_back(ch);
        }
    }
    if (content.size() > limit) out += "...";
    return out;
}

void fill_message_result(MessageResult& result, const JsonObject& payload) {
    result.ok = true;
    result.message_id = extract_string(payload, "message_id");
    result.sender_user_id = extract_string(payload, "sender_user_id");
    result.text = extract_string(payload, "text");
    result.created_at_ms = extract_number(payload, "created_at_ms");
    result.attachment_id = extract_string(payload, "attachment_id");
    result.filename = extract_string(payload, "filename");
    result.mime_type = extract_string(payload, "mime_type");
    result.size_bytes = extract_number(payload, "size_bytes");
    result.reply_to_message_id = extract_string(payload, "reply_to_message_id");
    result.forwarded_from_conversation_id = extract_string(payload, "forwarded_from_conversation_id");
    result.forwarded_from_message_id = extract_string(payload, "forwarded_from_message_id");
    result.forwarded_from_sender_user_id = extract_string(payload, "forwarded_from_sender_user_id");
    result.reaction_summary = extract_string(payload, "reaction_summary");
    result.pinned = extract_bool(payload, "pinned");
}

std::string extract_type(const std::string& line) {
    JsonParser parser(line);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) return {};
    return extract_string(*root.as_object(), "type");
}

std::optional<JsonObject> parse_payload(const std::string& line) {
    JsonParser parser(line);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) return std::nullopt;
    const auto* payload = find_member(*root.as_object(), "payload");
    if (!payload || !payload->is_object()) return std::nullopt;
    return *payload->as_object();
}

SyncedConversation parse_conversation_descriptor(const JsonObject& object) {
    SyncedConversation c;
    c.conversation_id = extract_string(object, "conversation_id");
    c.title = extract_string(object, "title");
    c.version = static_cast<int>(extract_number(object, "version"));
    c.next_before_message_id = extract_string(object, "next_before_message_id");
    c.has_more = extract_bool(object, "has_more");
    const auto* participants = find_member(object, "participant_user_ids");
    if (participants && participants->is_array()) {
        for (const auto& p : *participants->as_array()) {
            if (p.is_string()) c.participant_user_ids.push_back(*p.as_string());
        }
    }
    const auto* messages = find_member(object, "messages");
    if (messages && messages->is_array()) {
        for (const auto& m_val : *messages->as_array()) {
            if (!m_val.is_object()) continue;
            const auto* m_obj = m_val.as_object();
            SyncedMessage m;
            m.message_id = extract_string(*m_obj, "message_id");
            m.sender_user_id = extract_string(*m_obj, "sender_user_id");
            m.text = extract_string(*m_obj, "text");
            m.created_at_ms = extract_number(*m_obj, "created_at_ms");
            m.edited = extract_bool(*m_obj, "edited");
            m.deleted = extract_bool(*m_obj, "deleted");
            m.attachment_id = extract_string(*m_obj, "attachment_id");
            m.filename = extract_string(*m_obj, "filename");
            m.mime_type = extract_string(*m_obj, "mime_type");
            m.size_bytes = extract_number(*m_obj, "size_bytes");
            m.reply_to_message_id = extract_string(*m_obj, "reply_to_message_id");
            m.forwarded_from_conversation_id = extract_string(*m_obj, "forwarded_from_conversation_id");
            m.forwarded_from_message_id = extract_string(*m_obj, "forwarded_from_message_id");
            m.forwarded_from_sender_user_id = extract_string(*m_obj, "forwarded_from_sender_user_id");
            m.reaction_summary = extract_string(*m_obj, "reaction_summary");
            m.pinned = extract_bool(*m_obj, "pinned");
            c.messages.push_back(std::move(m));
        }
    }
    const auto* read_markers = find_member(object, "read_markers");
    if (read_markers && read_markers->is_object()) {
        for (const auto& [user_id, marker_val] : *read_markers->as_object()) {
            if (!marker_val.is_string()) continue;
            c.read_markers.push_back(ReadMarker {
                .user_id = user_id,
                .last_read_message_id = *marker_val.as_string(),
            });
        }
    }
    const auto* changes = find_member(object, "changes");
    if (changes && changes->is_array()) {
        for (const auto& change_val : *changes->as_array()) {
            if (!change_val.is_object()) continue;
            const auto* change_obj = change_val.as_object();
            SyncedChange change;
            change.version = static_cast<int>(extract_number(*change_obj, "version"));
            change.kind = extract_string(*change_obj, "kind");
            change.message_id = extract_string(*change_obj, "message_id");
            change.sender_user_id = extract_string(*change_obj, "sender_user_id");
            change.text = extract_string(*change_obj, "text");
            change.reader_user_id = extract_string(*change_obj, "reader_user_id");
            change.last_read_message_id = extract_string(*change_obj, "last_read_message_id");
            change.reply_to_message_id = extract_string(*change_obj, "reply_to_message_id");
            change.forwarded_from_conversation_id = extract_string(*change_obj, "forwarded_from_conversation_id");
            change.forwarded_from_message_id = extract_string(*change_obj, "forwarded_from_message_id");
            change.forwarded_from_sender_user_id = extract_string(*change_obj, "forwarded_from_sender_user_id");
            change.reaction_summary = extract_string(*change_obj, "reaction_summary");
            change.pinned = extract_bool(*change_obj, "pinned");
            c.changes.push_back(std::move(change));
        }
    }
    return c;
}

}  // namespace

ControlPlaneClient::ControlPlaneClient() = default;

ControlPlaneClient::~ControlPlaneClient() {
    disconnect();
}

bool ControlPlaneClient::connect(const std::string& host, unsigned short port) {
    if (!tcp_.connect(host, port)) {
        return false;
    }
    running_.store(true);
    dispatcher_ = std::thread(&ControlPlaneClient::dispatcher_loop, this);
    return true;
}

bool ControlPlaneClient::connect_tls(const std::string& host,
                                     unsigned short port,
                                     bool insecure_skip_verify,
                                     const std::string& server_name) {
    const auto verify_mode = insecure_skip_verify
        ? net::TcpLineClient::TlsVerifyMode::InsecureSkipVerify
        : net::TcpLineClient::TlsVerifyMode::SystemDefault;
    if (!tcp_.connect_tls(host, port, verify_mode, server_name)) {
        return false;
    }
    running_.store(true);
    dispatcher_ = std::thread(&ControlPlaneClient::dispatcher_loop, this);
    return true;
}

void ControlPlaneClient::disconnect() {
    running_.store(false);
    heartbeat_interval_ms_.store(0);
    tcp_.disconnect();
    if (dispatcher_.joinable()) dispatcher_.join();
    if (heartbeat_.joinable()) heartbeat_.join();
}

bool ControlPlaneClient::is_connected() const noexcept {
    return running_.load() && tcp_.is_connected();
}

void ControlPlaneClient::set_push_handler(PushHandler handler) {
    std::lock_guard lock(handler_mutex_);
    push_handler_ = std::move(handler);
}

void ControlPlaneClient::start_heartbeat(unsigned interval_ms) {
    heartbeat_interval_ms_.store(interval_ms);
    if (interval_ms == 0 || heartbeat_.joinable()) return;
    heartbeat_ = std::thread(&ControlPlaneClient::heartbeat_loop, this);
}

std::string ControlPlaneClient::next_correlation_id() {
    return "rpc_" + std::to_string(correlation_counter_.fetch_add(1) + 1);
}

int ControlPlaneClient::next_sequence() {
    return sequence_counter_.fetch_add(1) + 1;
}

std::string ControlPlaneClient::compose_envelope(const std::string& type,
                                                 const std::string& correlation_id,
                                                 const std::string& payload_body) {
    const int seq = sequence_counter_.fetch_add(1) + 1;
    std::ostringstream os;
    os << "{"
       << "\"type\":" << quote(type)
       << ",\"correlation_id\":" << quote(correlation_id)
       << ",\"session_id\":" << quote(session_id_)
       << ",\"actor_user_id\":" << quote(user_id_)
       << ",\"sequence\":" << seq
       << ",\"payload\":" << payload_body
       << "}";
    return os.str();
}

std::optional<std::string> ControlPlaneClient::send_and_wait(const std::string& type,
                                                             const std::string& payload_body) {
    const std::string corr = next_correlation_id();
    const std::string line = compose_envelope(type, corr, payload_body);
    if (!tcp_.send_line(line)) {
        return std::nullopt;
    }
    return tcp_.wait_for(net::TcpLineClient::match_correlation_id(corr), rpc_timeout_ms_);
}

LoginResult ControlPlaneClient::login(const std::string& username,
                                      const std::string& password,
                                      const std::string& device_id) {
    LoginResult result;
    std::string payload = "{";
    payload += "\"username\":" + quote(username);
    payload += ",\"password\":" + quote(password);
    payload += ",\"device_id\":" + quote(device_id);
    payload += "}";
    auto response = send_and_wait("login_request", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "login_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.session_id = extract_string(*payload_obj, "session_id");
    result.user_id = extract_string(*payload_obj, "user_id");
    result.display_name = extract_string(*payload_obj, "display_name");
    result.device_id = extract_string(*payload_obj, "device_id");
    session_id_ = result.session_id;
    user_id_ = result.user_id;
    return result;
}

RegisterResult ControlPlaneClient::register_user(const std::string& username,
                                                 const std::string& password,
                                                 const std::string& display_name,
                                                 const std::string& device_id) {
    RegisterResult result;
    std::string payload = "{";
    payload += "\"username\":" + quote(username);
    payload += ",\"password\":" + quote(password);
    payload += ",\"display_name\":" + quote(display_name.empty() ? username : display_name);
    payload += ",\"device_id\":" + quote(device_id);
    payload += ",\"device_label\":" + quote(device_id);
    payload += ",\"platform\":\"desktop\"";
    payload += "}";
    auto response = send_and_wait("register_request", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "register_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.session_id = extract_string(*payload_obj, "session_id");
    result.user_id = extract_string(*payload_obj, "user_id");
    result.display_name = extract_string(*payload_obj, "display_name");
    result.device_id = extract_string(*payload_obj, "device_id");
    session_id_ = result.session_id;
    user_id_ = result.user_id;
    return result;
}

SyncResult ControlPlaneClient::conversation_sync() {
    return conversation_sync_since({});
}

SyncResult ControlPlaneClient::conversation_sync_since(
    const std::vector<SyncCursor>& cursors) {
    SyncResult result;
    std::string payload = "{}";
    if (!cursors.empty()) {
        payload = "{\"cursors\":{";
        bool first = true;
        for (const auto& cursor : cursors) {
            if (cursor.conversation_id.empty() || cursor.last_message_id.empty()) continue;
            if (!first) payload += ",";
            first = false;
            payload += quote(cursor.conversation_id) + ":" + quote(cursor.last_message_id);
        }
        payload += "},\"versions\":{";
        bool first_version = true;
        for (const auto& cursor : cursors) {
            if (cursor.conversation_id.empty()) continue;
            if (!first_version) payload += ",";
            first_version = false;
            payload += quote(cursor.conversation_id) + ":" + std::to_string(cursor.version);
        }
        payload += "}}";
        if (first && first_version) payload = "{}";
    }
    auto response = send_and_wait("conversation_sync", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "conversation_sync") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    const auto* convs = find_member(*payload_obj, "conversations");
    if (!convs || !convs->is_array()) {
        result.ok = true;
        return result;
    }
    for (const auto& conv_val : *convs->as_array()) {
        if (!conv_val.is_object()) continue;
        result.conversations.push_back(parse_conversation_descriptor(*conv_val.as_object()));
    }
    result.ok = true;
    return result;
}

SyncResult ControlPlaneClient::conversation_history_page(const std::string& conversation_id,
                                                         const std::string& before_message_id,
                                                         int limit) {
    SyncResult result;
    std::string payload = "{\"history_limits\":{"
                        + quote(conversation_id) + ":" + std::to_string(limit) + "}";
    if (!before_message_id.empty()) {
        payload += ",\"before_message_ids\":{"
                 + quote(conversation_id) + ":" + quote(before_message_id) + "}";
    }
    payload += "}";
    auto response = send_and_wait("conversation_sync", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "conversation_sync") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    const auto* convs = find_member(*payload_obj, "conversations");
    if (convs && convs->is_array()) {
        for (const auto& conv_val : *convs->as_array()) {
            if (!conv_val.is_object()) continue;
            result.conversations.push_back(parse_conversation_descriptor(*conv_val.as_object()));
        }
    }
    result.ok = true;
    return result;
}

MessageResult ControlPlaneClient::send_message(const std::string& conversation_id,
                                               const std::string& text) {
    return reply_message(conversation_id, "", text);
}

MessageResult ControlPlaneClient::reply_message(const std::string& conversation_id,
                                                const std::string& reply_to_message_id,
                                                const std::string& text) {
    MessageResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"text\":" + quote(text);
    if (!reply_to_message_id.empty()) {
        payload += ",\"reply_to_message_id\":" + quote(reply_to_message_id);
    }
    payload += "}";
    auto response = send_and_wait("message_send", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_deliver") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    fill_message_result(result, *payload_obj);
    return result;
}

MessageResult ControlPlaneClient::forward_message(const std::string& source_conversation_id,
                                                  const std::string& source_message_id,
                                                  const std::string& target_conversation_id) {
    MessageResult result;
    std::string payload = "{\"source_conversation_id\":" + quote(source_conversation_id)
                        + ",\"source_message_id\":" + quote(source_message_id)
                        + ",\"target_conversation_id\":" + quote(target_conversation_id) + "}";
    auto response = send_and_wait("message_forward", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_deliver") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    fill_message_result(result, *payload_obj);
    return result;
}

MessageReactionResult ControlPlaneClient::toggle_reaction(const std::string& conversation_id,
                                                          const std::string& message_id,
                                                          const std::string& emoji) {
    MessageReactionResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"message_id\":" + quote(message_id)
                        + ",\"emoji\":" + quote(emoji) + "}";
    auto response = send_and_wait("message_reaction", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_reaction_updated") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.conversation_id = extract_string(*payload_obj, "conversation_id");
    result.message_id = extract_string(*payload_obj, "message_id");
    result.actor_user_id = extract_string(*payload_obj, "actor_user_id");
    result.emoji = extract_string(*payload_obj, "emoji");
    result.reaction_summary = extract_string(*payload_obj, "reaction_summary");
    return result;
}

MessagePinResult ControlPlaneClient::set_message_pin(const std::string& conversation_id,
                                                     const std::string& message_id,
                                                     bool pinned) {
    MessagePinResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"message_id\":" + quote(message_id)
                        + ",\"pinned\":" + (pinned ? "true" : "false") + "}";
    auto response = send_and_wait("message_pin", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_pin_updated") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.conversation_id = extract_string(*payload_obj, "conversation_id");
    result.message_id = extract_string(*payload_obj, "message_id");
    result.actor_user_id = extract_string(*payload_obj, "actor_user_id");
    result.pinned = extract_bool(*payload_obj, "pinned");
    return result;
}

MessageResult ControlPlaneClient::send_attachment(const std::string& conversation_id,
                                                  const std::string& caption,
                                                  const std::string& filename,
                                                  const std::string& mime_type,
                                                  const std::string& content) {
    MessageResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"caption\":" + quote(caption)
                        + ",\"filename\":" + quote(filename)
                        + ",\"mime_type\":" + quote(mime_type.empty() ? "application/octet-stream" : mime_type)
                        + ",\"content_b64\":" + quote(base64_encode(content))
                        + ",\"size_bytes\":" + std::to_string(content.size()) + "}";
    auto response = send_and_wait("message_send_attachment", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_deliver") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    fill_message_result(result, *payload_obj);
    if (starts_with(result.mime_type, "text/")) {
        result.preview_text = text_preview(content);
    }
    return result;
}

MessageResult ControlPlaneClient::send_attachment_chunked(
    const std::string& conversation_id,
    const std::string& caption,
    const std::string& filename,
    const std::string& mime_type,
    const std::string& content,
    ChunkedUploadProgressCallback progress,
    std::size_t chunk_size) {
    MessageResult result;

    // ---- 1. init ----
    const std::string init_payload =
        "{\"conversation_id\":" + quote(conversation_id)
      + ",\"filename\":" + quote(filename)
      + ",\"mime_type\":" + quote(mime_type.empty() ? "application/octet-stream" : mime_type)
      + ",\"total_size_bytes\":" + std::to_string(content.size()) + "}";
    auto init_resp = send_and_wait("attachment_upload_init_request", init_payload);
    if (!init_resp) { result.error_code = "transport_error"; return result; }
    auto init_obj = parse_payload(*init_resp);
    if (!init_obj || extract_type(*init_resp) != "attachment_upload_init_response") {
        if (init_obj) {
            result.error_code = extract_string(*init_obj, "code");
            result.error_message = extract_string(*init_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
        return result;
    }
    const std::string upload_id = extract_string(*init_obj, "upload_id");
    if (upload_id.empty()) { result.error_code = "bad_response"; return result; }
    // Server may suggest a chunk_size; honour it when smaller than ours.
    const auto server_chunk = static_cast<std::size_t>(extract_number(*init_obj, "chunk_size"));
    if (server_chunk > 0 && server_chunk < chunk_size) chunk_size = server_chunk;
    if (chunk_size == 0) chunk_size = 256 * 1024;

    // ---- 2. chunks ----
    const std::size_t total = content.size();
    if (progress) progress(0, total);
    std::size_t offset = 0;
    int sequence = 0;
    while (offset < total) {
        // Parenthesise std::min so MSVC's <windows.h> `min` macro doesn't
        // intercept the call — Schannel headers in our TLS path pull it in.
        const std::size_t this_chunk = (std::min)(chunk_size, total - offset);
        const std::string body = content.substr(offset, this_chunk);
        const std::string chunk_payload =
            "{\"upload_id\":" + quote(upload_id)
          + ",\"sequence\":" + std::to_string(sequence)
          + ",\"content_b64\":" + quote(base64_encode(body)) + "}";
        auto chunk_resp = send_and_wait("attachment_upload_chunk_request", chunk_payload);
        if (!chunk_resp) { result.error_code = "transport_error"; return result; }
        auto chunk_obj = parse_payload(*chunk_resp);
        if (!chunk_obj || extract_type(*chunk_resp) != "attachment_upload_chunk_ack") {
            if (chunk_obj) {
                result.error_code = extract_string(*chunk_obj, "code");
                result.error_message = extract_string(*chunk_obj, "message");
            } else {
                result.error_code = "bad_response";
            }
            return result;
        }
        offset += this_chunk;
        if (progress) progress(offset, total);
        ++sequence;
    }

    // ---- 3. complete ----
    const std::string complete_payload =
        "{\"upload_id\":" + quote(upload_id)
      + ",\"caption\":" + quote(caption) + "}";
    auto complete_resp = send_and_wait("attachment_upload_complete_request", complete_payload);
    if (!complete_resp) { result.error_code = "transport_error"; return result; }
    auto complete_obj = parse_payload(*complete_resp);
    if (!complete_obj || extract_type(*complete_resp) != "message_deliver") {
        if (complete_obj) {
            result.error_code = extract_string(*complete_obj, "code");
            result.error_message = extract_string(*complete_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
        return result;
    }
    fill_message_result(result, *complete_obj);
    return result;
}

AttachmentFetchResult ControlPlaneClient::fetch_attachment(const std::string& attachment_id) {
    AttachmentFetchResult result;
    std::string payload = "{\"attachment_id\":" + quote(attachment_id) + "}";
    auto response = send_and_wait("attachment_fetch_request", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "attachment_fetch_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.attachment_id = extract_string(*payload_obj, "attachment_id");
    result.conversation_id = extract_string(*payload_obj, "conversation_id");
    result.uploader_user_id = extract_string(*payload_obj, "uploader_user_id");
    result.filename = extract_string(*payload_obj, "filename");
    result.mime_type = extract_string(*payload_obj, "mime_type");
    result.size_bytes = extract_number(*payload_obj, "size_bytes");
    result.content = base64_decode(extract_string(*payload_obj, "content_b64"));
    return result;
}

AckResult ControlPlaneClient::send_typing_pulse(const std::string& conversation_id,
                                                bool is_typing) {
    // M147: pure passthrough — server fanouts to other participants.
    // Callers typically fire-and-forget; we still parse the response so
    // a CONVERSATION_ACCESS_DENIED / UNKNOWN_CONVERSATION can surface
    // through ok=false on the caller side.
    AckResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"is_typing\":" + (is_typing ? "true" : "false") + "}";
    auto response = send_and_wait("typing_pulse", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type == "typing_pulse") {
        result.ok = true;
    } else {
        auto payload_obj = parse_payload(*response);
        if (payload_obj) {
            result.error_code = extract_string(*payload_obj, "code");
            result.error_message = extract_string(*payload_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
    }
    return result;
}

AckResult ControlPlaneClient::mark_read(const std::string& conversation_id,
                                        const std::string& message_id) {
    AckResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"message_id\":" + quote(message_id) + "}";
    auto response = send_and_wait("message_read", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type == "message_read_update") {
        result.ok = true;
    } else {
        auto payload_obj = parse_payload(*response);
        if (payload_obj) {
            result.error_code = extract_string(*payload_obj, "code");
            result.error_message = extract_string(*payload_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
    }
    return result;
}

MessageResult ControlPlaneClient::edit_message(const std::string& conversation_id,
                                               const std::string& message_id,
                                               const std::string& new_text) {
    MessageResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"message_id\":" + quote(message_id)
                        + ",\"text\":" + quote(new_text) + "}";
    auto response = send_and_wait("message_edit", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "message_edited") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.message_id = extract_string(*payload_obj, "message_id");
    result.sender_user_id = extract_string(*payload_obj, "sender_user_id");
    result.text = extract_string(*payload_obj, "text");
    return result;
}

AckResult ControlPlaneClient::delete_message(const std::string& conversation_id,
                                             const std::string& message_id) {
    AckResult result;
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"message_id\":" + quote(message_id) + "}";
    auto response = send_and_wait("message_delete", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type == "message_deleted") {
        result.ok = true;
    } else {
        auto payload_obj = parse_payload(*response);
        if (payload_obj) {
            result.error_code = extract_string(*payload_obj, "code");
            result.error_message = extract_string(*payload_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
    }
    return result;
}

namespace {
ContactListResult parse_contact_list(const std::string& response) {
    ContactListResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    std::string type = extract_type(response);
    if (type != "contact_list_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    const auto* contacts = find_member(*payload_obj, "contacts");
    if (contacts && contacts->is_array()) {
        for (const auto& c_val : *contacts->as_array()) {
            if (!c_val.is_object()) continue;
            const auto* c_obj = c_val.as_object();
            ContactEntry e;
            e.user_id = extract_string(*c_obj, "user_id");
            e.display_name = extract_string(*c_obj, "display_name");
            e.online = extract_bool(*c_obj, "online");
            result.contacts.push_back(std::move(e));
        }
    }
    return result;
}

ProfileResult parse_profile_response(const std::string& response) {
    ProfileResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(response);
    if (type != "profile_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.user_id = extract_string(*payload_obj, "user_id");
    result.username = extract_string(*payload_obj, "username");
    result.display_name = extract_string(*payload_obj, "display_name");
    return result;
}

UserSearchResult parse_user_search_response(const std::string& response) {
    UserSearchResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(response);
    if (type != "user_search_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    const auto* results = find_member(*payload_obj, "results");
    if (results && results->is_array()) {
        for (const auto& u_val : *results->as_array()) {
            if (!u_val.is_object()) continue;
            const auto* u_obj = u_val.as_object();
            UserSearchEntry e;
            e.user_id = extract_string(*u_obj, "user_id");
            e.username = extract_string(*u_obj, "username");
            e.display_name = extract_string(*u_obj, "display_name");
            e.online = extract_bool(*u_obj, "online");
            e.is_contact = extract_bool(*u_obj, "is_contact");
            result.results.push_back(std::move(e));
        }
    }
    return result;
}

MessageSearchResult parse_message_search_response(const std::string& response) {
    MessageSearchResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(response);
    if (type != "message_search_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.next_offset = static_cast<int>(extract_number(*payload_obj, "next_offset"));
    result.has_more = extract_bool(*payload_obj, "has_more");
    const auto* results = find_member(*payload_obj, "results");
    if (results && results->is_array()) {
        for (const auto& value : *results->as_array()) {
            if (!value.is_object()) continue;
            const auto* object = value.as_object();
            MessageSearchEntry entry;
            entry.conversation_id = extract_string(*object, "conversation_id");
            entry.conversation_title = extract_string(*object, "conversation_title");
            entry.message_id = extract_string(*object, "message_id");
            entry.sender_user_id = extract_string(*object, "sender_user_id");
            entry.text = extract_string(*object, "text");
            entry.created_at_ms = extract_number(*object, "created_at_ms");
            entry.attachment_id = extract_string(*object, "attachment_id");
            entry.filename = extract_string(*object, "filename");
            entry.snippet = extract_string(*object, "snippet");
            result.results.push_back(std::move(entry));
        }
    }
    return result;
}

DeviceListResult parse_device_list_response(const std::string& response) {
    DeviceListResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(response);
    if (type != "device_list_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    const auto* devices = find_member(*payload_obj, "devices");
    if (devices && devices->is_array()) {
        for (const auto& d_val : *devices->as_array()) {
            if (!d_val.is_object()) continue;
            const auto* d_obj = d_val.as_object();
            DeviceEntry d;
            d.device_id = extract_string(*d_obj, "device_id");
            d.label = extract_string(*d_obj, "label");
            d.platform = extract_string(*d_obj, "platform");
            d.trusted = extract_bool(*d_obj, "trusted");
            d.active = extract_bool(*d_obj, "active");
            result.devices.push_back(std::move(d));
        }
    }
    return result;
}
}

ContactListResult ControlPlaneClient::list_contacts() {
    auto response = send_and_wait("contact_list_request", "{}");
    if (!response) {
        ContactListResult r;
        r.error_code = "transport_error";
        return r;
    }
    return parse_contact_list(*response);
}

ContactListResult ControlPlaneClient::add_contact(const std::string& target_user_id) {
    std::string payload = "{\"target_user_id\":" + quote(target_user_id) + "}";
    auto response = send_and_wait("contact_add", payload);
    if (!response) {
        ContactListResult r;
        r.error_code = "transport_error";
        return r;
    }
    return parse_contact_list(*response);
}

ContactListResult ControlPlaneClient::remove_contact(const std::string& target_user_id) {
    std::string payload = "{\"target_user_id\":" + quote(target_user_id) + "}";
    auto response = send_and_wait("contact_remove", payload);
    if (!response) {
        ContactListResult r;
        r.error_code = "transport_error";
        return r;
    }
    return parse_contact_list(*response);
}

ProfileResult ControlPlaneClient::profile_get() {
    auto response = send_and_wait("profile_get_request", "{}");
    if (!response) {
        ProfileResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_profile_response(*response);
}

ProfileResult ControlPlaneClient::profile_update(const std::string& display_name) {
    auto response = send_and_wait("profile_update_request", "{\"display_name\":" + quote(display_name) + "}");
    if (!response) {
        ProfileResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_profile_response(*response);
}

UserSearchResult ControlPlaneClient::search_users(const std::string& query, int limit) {
    std::string payload = "{\"query\":" + quote(query)
                        + ",\"limit\":" + std::to_string(limit) + "}";
    auto response = send_and_wait("user_search_request", payload);
    if (!response) {
        UserSearchResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_user_search_response(*response);
}

MessageSearchResult ControlPlaneClient::search_messages(const std::string& query,
                                                        const std::string& conversation_id,
                                                        int limit,
                                                        int offset) {
    std::string payload = "{\"query\":" + quote(query)
                        + ",\"conversation_id\":" + quote(conversation_id)
                        + ",\"limit\":" + std::to_string(limit)
                        + ",\"offset\":" + std::to_string(offset) + "}";
    auto response = send_and_wait("message_search_request", payload);
    if (!response) {
        MessageSearchResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_message_search_response(*response);
}

namespace {
ConversationActionResult parse_conversation_action_response(const std::string& response) {
    ConversationActionResult result;
    auto payload_obj = parse_payload(response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(response);
    if (type != "conversation_updated") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    result.conversation = parse_conversation_descriptor(*payload_obj);
    return result;
}
}

ConversationActionResult ControlPlaneClient::create_conversation(
    const std::vector<std::string>& participant_user_ids,
    const std::string& title) {
    std::string payload = "{\"participant_user_ids\":[";
    for (std::size_t i = 0; i < participant_user_ids.size(); ++i) {
        if (i > 0) payload += ",";
        payload += quote(participant_user_ids[i]);
    }
    payload += "],\"title\":" + quote(title) + "}";
    auto response = send_and_wait("conversation_create", payload);
    if (!response) {
        ConversationActionResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_conversation_action_response(*response);
}

ConversationActionResult ControlPlaneClient::add_conversation_participant(
    const std::string& conversation_id,
    const std::string& user_id) {
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"user_id\":" + quote(user_id) + "}";
    auto response = send_and_wait("conversation_add_participant", payload);
    if (!response) {
        ConversationActionResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_conversation_action_response(*response);
}

ConversationActionResult ControlPlaneClient::remove_conversation_participant(
    const std::string& conversation_id,
    const std::string& user_id) {
    std::string payload = "{\"conversation_id\":" + quote(conversation_id)
                        + ",\"user_id\":" + quote(user_id) + "}";
    auto response = send_and_wait("conversation_remove_participant", payload);
    if (!response) {
        ConversationActionResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_conversation_action_response(*response);
}

DeviceListResult ControlPlaneClient::list_devices() {
    auto response = send_and_wait("device_list_request", "{}");
    if (!response) {
        DeviceListResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_device_list_response(*response);
}

DeviceListResult ControlPlaneClient::revoke_device(const std::string& device_id) {
    auto response = send_and_wait("device_revoke_request", "{\"device_id\":" + quote(device_id) + "}");
    if (!response) {
        DeviceListResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_device_list_response(*response);
}

DeviceListResult ControlPlaneClient::update_device_trust(const std::string& device_id, bool trusted) {
    std::string payload = "{\"device_id\":" + quote(device_id)
                        + ",\"trusted\":" + (trusted ? "true" : "false") + "}";
    auto response = send_and_wait("device_trust_update_request", payload);
    if (!response) {
        DeviceListResult result;
        result.error_code = "transport_error";
        return result;
    }
    return parse_device_list_response(*response);
}

PresenceResult ControlPlaneClient::presence_query(const std::vector<std::string>& user_ids) {
    PresenceResult result;
    std::string payload = "{\"user_ids\":[";
    for (std::size_t i = 0; i < user_ids.size(); ++i) {
        if (i > 0) payload += ",";
        payload += quote(user_ids[i]);
    }
    payload += "]}";
    auto response = send_and_wait("presence_query_request", payload);
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    auto payload_obj = parse_payload(*response);
    if (!payload_obj) {
        result.error_code = "bad_response";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type != "presence_query_response") {
        result.error_code = extract_string(*payload_obj, "code");
        result.error_message = extract_string(*payload_obj, "message");
        return result;
    }
    result.ok = true;
    const auto* users = find_member(*payload_obj, "users");
    if (users && users->is_array()) {
        for (const auto& u_val : *users->as_array()) {
            if (!u_val.is_object()) continue;
            const auto* u_obj = u_val.as_object();
            PresenceUser u;
            u.user_id = extract_string(*u_obj, "user_id");
            u.online = extract_bool(*u_obj, "online");
            u.last_seen_at_ms = extract_number(*u_obj, "last_seen_at_ms");
            result.users.push_back(std::move(u));
        }
    }
    return result;
}

AckResult ControlPlaneClient::heartbeat_ping() {
    AckResult result;
    auto response = send_and_wait("heartbeat_ping", "{\"client_timestamp_ms\":0}");
    if (!response) {
        result.error_code = "transport_error";
        return result;
    }
    const std::string type = extract_type(*response);
    if (type == "heartbeat_ack") {
        result.ok = true;
    } else {
        auto payload_obj = parse_payload(*response);
        if (payload_obj) {
            result.error_code = extract_string(*payload_obj, "code");
            result.error_message = extract_string(*payload_obj, "message");
        } else {
            result.error_code = "bad_response";
        }
    }
    return result;
}

void ControlPlaneClient::dispatcher_loop() {
    auto push_predicate = [](const std::string& line) { return is_push_line(line); };
    while (running_.load()) {
        auto frame = tcp_.wait_for(push_predicate, 500);
        if (!frame) continue;
        PushHandler handler_copy;
        {
            std::lock_guard lock(handler_mutex_);
            handler_copy = push_handler_;
        }
        if (!handler_copy) continue;
        const std::string type = extract_type(*frame);
        handler_copy(type, *frame);
    }
}

void ControlPlaneClient::heartbeat_loop() {
    while (running_.load()) {
        const unsigned interval = heartbeat_interval_ms_.load();
        if (interval == 0) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(interval));
        if (!running_.load() || heartbeat_interval_ms_.load() == 0) break;
        (void)heartbeat_ping();
    }
}

// ---- Remote-control RPCs ----

namespace {

template <typename Result>
void capture_error(Result& result, const JsonObject* payload_obj, const std::string& fallback) {
    if (payload_obj == nullptr) {
        result.error_code = fallback;
        return;
    }
    result.error_code = extract_string(*payload_obj, "code");
    result.error_message = extract_string(*payload_obj, "message");
}

}  // namespace

RemoteSessionStateResult ControlPlaneClient::remote_invite(
    const std::string& requester_device_id,
    const std::string& target_device_id) {
    RemoteSessionStateResult result;
    const std::string payload =
        "{\"requester_device_id\":" + quote(requester_device_id)
        + ",\"target_device_id\":" + quote(target_device_id) + "}";
    auto response = send_and_wait("remote_invite", payload);
    if (!response) { result.error_code = "transport_error"; return result; }
    auto payload_obj = parse_payload(*response);
    const std::string type = extract_type(*response);
    if (type != "remote_session_state" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.remote_session_id = extract_string(*payload_obj, "remote_session_id");
    result.state = extract_string(*payload_obj, "state");
    result.target_user_id = extract_string(*payload_obj, "target_user_id");
    result.target_device_id = extract_string(*payload_obj, "target_device_id");
    return result;
}

RemoteRelayAssignmentResult ControlPlaneClient::remote_approve(
    const std::string& remote_session_id) {
    RemoteRelayAssignmentResult result;
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id) + "}";
    auto response = send_and_wait("remote_approve", payload);
    if (!response) { result.error_code = "transport_error"; return result; }
    auto payload_obj = parse_payload(*response);
    const std::string type = extract_type(*response);
    if (type != "remote_relay_assignment" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.remote_session_id = extract_string(*payload_obj, "remote_session_id");
    result.state = extract_string(*payload_obj, "state");
    result.relay_region = extract_string(*payload_obj, "relay_region");
    result.relay_endpoint = extract_string(*payload_obj, "relay_endpoint");
    return result;
}

namespace {
RemoteSessionTerminatedResult parse_terminated(const std::string& response) {
    RemoteSessionTerminatedResult result;
    auto payload_obj = parse_payload(response);
    const std::string type = extract_type(response);
    if (type != "remote_session_terminated" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.remote_session_id = extract_string(*payload_obj, "remote_session_id");
    result.state = extract_string(*payload_obj, "state");
    result.detail = extract_string(*payload_obj, "detail");
    return result;
}
}  // namespace

RemoteSessionTerminatedResult ControlPlaneClient::remote_reject(
    const std::string& remote_session_id) {
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id) + "}";
    auto response = send_and_wait("remote_reject", payload);
    if (!response) { RemoteSessionTerminatedResult r; r.error_code = "transport_error"; return r; }
    return parse_terminated(*response);
}

RemoteSessionTerminatedResult ControlPlaneClient::remote_cancel(
    const std::string& remote_session_id) {
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id) + "}";
    auto response = send_and_wait("remote_cancel", payload);
    if (!response) { RemoteSessionTerminatedResult r; r.error_code = "transport_error"; return r; }
    return parse_terminated(*response);
}

RemoteSessionTerminatedResult ControlPlaneClient::remote_terminate(
    const std::string& remote_session_id) {
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id) + "}";
    auto response = send_and_wait("remote_terminate", payload);
    if (!response) { RemoteSessionTerminatedResult r; r.error_code = "transport_error"; return r; }
    return parse_terminated(*response);
}

RemoteSessionTerminatedResult ControlPlaneClient::remote_disconnect(
    const std::string& remote_session_id,
    const std::string& reason) {
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id)
        + ",\"reason\":" + quote(reason) + "}";
    auto response = send_and_wait("remote_disconnect", payload);
    if (!response) { RemoteSessionTerminatedResult r; r.error_code = "transport_error"; return r; }
    return parse_terminated(*response);
}

RemoteRendezvousResult ControlPlaneClient::remote_rendezvous_request(
    const std::string& remote_session_id) {
    RemoteRendezvousResult result;
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id) + "}";
    auto response = send_and_wait("remote_rendezvous_request", payload);
    if (!response) { result.error_code = "transport_error"; return result; }
    auto payload_obj = parse_payload(*response);
    const std::string type = extract_type(*response);
    if (type != "remote_rendezvous_info" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.remote_session_id = extract_string(*payload_obj, "remote_session_id");
    result.state = extract_string(*payload_obj, "state");
    result.relay_region = extract_string(*payload_obj, "relay_region");
    result.relay_endpoint = extract_string(*payload_obj, "relay_endpoint");
    result.relay_key_b64 = extract_string(*payload_obj, "relay_key_b64");
    const auto* candidates = find_member(*payload_obj, "candidates");
    if (candidates && candidates->is_array()) {
        for (const auto& cand_val : *candidates->as_array()) {
            if (!cand_val.is_object()) continue;
            const auto* cand = cand_val.as_object();
            RemoteRendezvousCandidate c;
            c.kind = extract_string(*cand, "kind");
            c.address = extract_string(*cand, "address");
            c.port = static_cast<int>(extract_number(*cand, "port"));
            c.priority = static_cast<int>(extract_number(*cand, "priority"));
            result.candidates.push_back(std::move(c));
        }
    }
    return result;
}

namespace {
CallStateResult parse_call_state(const std::string& response) {
    CallStateResult result;
    auto payload_obj = parse_payload(response);
    const std::string type = extract_type(response);
    if (type != "call_state" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.call_id = extract_string(*payload_obj, "call_id");
    result.state = extract_string(*payload_obj, "state");
    result.kind = extract_string(*payload_obj, "kind");
    result.detail = extract_string(*payload_obj, "detail");
    return result;
}
}  // namespace

CallStateResult ControlPlaneClient::call_invite(
    const std::string& callee_user_id,
    const std::string& callee_device_id,
    const std::string& kind) {
    const std::string payload =
        "{\"callee_user_id\":" + quote(callee_user_id)
        + ",\"callee_device_id\":" + quote(callee_device_id)
        + ",\"kind\":" + quote(kind) + "}";
    auto response = send_and_wait("call_invite_request", payload);
    if (!response) { CallStateResult r; r.error_code = "transport_error"; return r; }
    return parse_call_state(*response);
}

CallStateResult ControlPlaneClient::call_accept(const std::string& call_id) {
    const std::string payload = "{\"call_id\":" + quote(call_id) + "}";
    auto response = send_and_wait("call_accept_request", payload);
    if (!response) { CallStateResult r; r.error_code = "transport_error"; return r; }
    return parse_call_state(*response);
}

CallStateResult ControlPlaneClient::call_decline(const std::string& call_id) {
    const std::string payload = "{\"call_id\":" + quote(call_id) + "}";
    auto response = send_and_wait("call_decline_request", payload);
    if (!response) { CallStateResult r; r.error_code = "transport_error"; return r; }
    return parse_call_state(*response);
}

CallStateResult ControlPlaneClient::call_end(const std::string& call_id) {
    const std::string payload = "{\"call_id\":" + quote(call_id) + "}";
    auto response = send_and_wait("call_end_request", payload);
    if (!response) { CallStateResult r; r.error_code = "transport_error"; return r; }
    return parse_call_state(*response);
}

RemoteInputAckResult ControlPlaneClient::remote_input_event(
    const std::string& remote_session_id,
    const std::string& kind,
    const std::string& data_json) {
    RemoteInputAckResult result;
    const std::string body = data_json.empty() ? std::string("{}") : data_json;
    const std::string payload =
        "{\"remote_session_id\":" + quote(remote_session_id)
        + ",\"kind\":" + quote(kind)
        + ",\"data\":" + body + "}";
    auto response = send_and_wait("remote_input_event", payload);
    if (!response) { result.error_code = "transport_error"; return result; }
    auto payload_obj = parse_payload(*response);
    const std::string type = extract_type(*response);
    if (type != "remote_input_ack" || !payload_obj) {
        capture_error(result, payload_obj ? &*payload_obj : nullptr, "bad_response");
        return result;
    }
    result.ok = true;
    result.remote_session_id = extract_string(*payload_obj, "remote_session_id");
    result.sequence = static_cast<int>(extract_number(*payload_obj, "sequence"));
    result.kind = extract_string(*payload_obj, "kind");
    return result;
}

}  // namespace telegram_like::client::transport
