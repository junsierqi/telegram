#include "app_desktop/desktop_chat_store.h"

#include "transport/json_value.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string_view>
#include <utility>

namespace telegram_like::client::app_desktop {

namespace {

using telegram_like::client::transport::JsonObject;
using telegram_like::client::transport::JsonArray;
using telegram_like::client::transport::JsonParser;
using telegram_like::client::transport::JsonValue;
using telegram_like::client::transport::find_member;
using telegram_like::client::transport::string_or_empty;

std::string extract_payload_string(const std::string& envelope, std::string_view key) {
    JsonParser parser(envelope);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) return {};
    const auto* payload = find_member(*root.as_object(), "payload");
    if (!payload || !payload->is_object()) return {};
    return string_or_empty(*payload->as_object(), key);
}

bool extract_bool(const JsonObject& object, std::string_view key, bool fallback = false) {
    const auto* value = find_member(object, key);
    if (value == nullptr) return fallback;
    if (const auto* boolean = std::get_if<bool>(&value->storage)) return *boolean;
    return fallback;
}

std::size_t extract_size(const JsonObject& object, std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) return 0;
    if (const auto* number = std::get_if<double>(&value->storage)) {
        return *number < 0 ? 0 : static_cast<std::size_t>(*number);
    }
    return 0;
}

std::size_t extract_payload_size(const std::string& envelope, std::string_view key) {
    JsonParser parser(envelope);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) return 0;
    const auto* payload = find_member(*root.as_object(), "payload");
    if (!payload || !payload->is_object()) return 0;
    return extract_size(*payload->as_object(), key);
}

long long extract_number(const JsonObject& object, std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) return 0;
    if (const auto* number = std::get_if<double>(&value->storage)) {
        return static_cast<long long>(*number);
    }
    return 0;
}

long long extract_payload_number(const std::string& envelope, std::string_view key) {
    JsonParser parser(envelope);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) return 0;
    const auto* payload = find_member(*root.as_object(), "payload");
    if (!payload || !payload->is_object()) return 0;
    return extract_number(*payload->as_object(), key);
}

std::string json_escape(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            out += static_cast<unsigned char>(ch) < 0x20 ? ' ' : ch;
            break;
        }
    }
    return out;
}

std::string html_escape(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
        case '&': out += "&amp;"; break;
        case '<': out += "&lt;"; break;
        case '>': out += "&gt;"; break;
        case '"': out += "&quot;"; break;
        case '\n': out += "<br>"; break;
        case '\r': break;
        default:
            out += static_cast<unsigned char>(ch) < 0x20 ? ' ' : ch;
            break;
        }
    }
    return out;
}

void write_string(std::ostream& out, std::string_view value) {
    out << '"' << json_escape(value) << '"';
}

bool starts_with(std::string_view value, std::string_view prefix) {
    return value.size() >= prefix.size() && value.substr(0, prefix.size()) == prefix;
}

std::string lower_copy(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (const unsigned char ch : value) {
        out.push_back(static_cast<char>(std::tolower(ch)));
    }
    return out;
}

bool contains_case_insensitive(std::string_view haystack, std::string_view needle) {
    if (needle.empty()) return true;
    return lower_copy(haystack).find(lower_copy(needle)) != std::string::npos;
}

bool message_matches_query(const DesktopMessage& message, std::string_view query) {
    if (query.empty()) return true;
    return contains_case_insensitive(message.message_id, query)
        || contains_case_insensitive(message.sender_user_id, query)
        || contains_case_insensitive(message.text, query)
        || contains_case_insensitive(message.filename, query)
        || contains_case_insensitive(message.mime_type, query)
        || contains_case_insensitive(message.preview_text, query)
        || contains_case_insensitive(message.reply_to_message_id, query)
        || contains_case_insensitive(message.forwarded_from_message_id, query)
        || contains_case_insensitive(message.reaction_summary, query);
}

std::string message_search_snippet(const DesktopMessage& message) {
    std::string text = message.deleted ? "<deleted>" : message.text;
    if (text.empty() && !message.filename.empty()) text = message.filename;
    if (text.empty()) text = message.message_id;
    if (text.size() > 80) text = text.substr(0, 77) + "...";
    return text;
}

std::string preview_label(const DesktopMessage& message) {
    if (!message.preview_text.empty()) {
        return " preview=\"" + message.preview_text + "\"";
    }
    if (starts_with(message.mime_type, "image/")) {
        return " preview=image";
    }
    if (starts_with(message.mime_type, "text/")) {
        return " preview=text";
    }
    return {};
}

int message_order_key(std::string_view message_id) {
    const auto pos = message_id.rfind('_');
    if (pos == std::string_view::npos || pos + 1 >= message_id.size()) return 0;
    int value = 0;
    for (std::size_t i = pos + 1; i < message_id.size(); ++i) {
        const char ch = message_id[i];
        if (ch < '0' || ch > '9') return 0;
        value = value * 10 + (ch - '0');
    }
    return value;
}

std::string format_time(long long created_at_ms) {
    if (created_at_ms <= 0) return "legacy";
    const std::time_t seconds = static_cast<std::time_t>(created_at_ms / 1000);
    std::tm tm {};
#if defined(_WIN32)
    localtime_s(&tm, &seconds);
#else
    localtime_r(&seconds, &tm);
#endif
    std::ostringstream out;
    out << std::setfill('0') << std::setw(2) << tm.tm_hour << ":"
        << std::setfill('0') << std::setw(2) << tm.tm_min;
    return out.str();
}

long long now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

bool has_peer_read(const DesktopConversation& conversation,
                   const DesktopMessage& message,
                   const std::string& current_user_id) {
    if (message.sender_user_id != current_user_id || message.message_id.empty()) return false;
    const int message_key = message_order_key(message.message_id);
    for (const auto& marker : conversation.read_markers) {
        if (marker.user_id.empty() || marker.user_id == current_user_id) continue;
        if (marker.last_read_message_id == message.message_id) return true;
        const int marker_key = message_order_key(marker.last_read_message_id);
        if (message_key > 0 && marker_key >= message_key) return true;
    }
    return false;
}

std::vector<std::string> readers_for(const DesktopConversation& conversation,
                                     const DesktopMessage& message,
                                     const std::string& current_user_id) {
    std::vector<std::string> readers;
    if (message.sender_user_id != current_user_id || message.message_id.empty()
        || message.delivery_state == "pending" || message.delivery_state == "failed") {
        return readers;
    }
    const int message_key = message_order_key(message.message_id);
    for (const auto& marker : conversation.read_markers) {
        if (marker.user_id.empty() || marker.user_id == current_user_id) continue;
        if (marker.last_read_message_id == message.message_id) {
            readers.push_back(marker.user_id);
            continue;
        }
        const int marker_key = message_order_key(marker.last_read_message_id);
        if (message_key > 0 && marker_key >= message_key) readers.push_back(marker.user_id);
    }
    std::sort(readers.begin(), readers.end());
    readers.erase(std::unique(readers.begin(), readers.end()), readers.end());
    return readers;
}

std::string join_strings(const std::vector<std::string>& values, std::string_view sep) {
    std::string out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) out += sep;
        out += values[i];
    }
    return out;
}

std::string status_label(const DesktopConversation& conversation,
                         const DesktopMessage& message,
                         const std::string& current_user_id) {
    if (message.sender_user_id != current_user_id) return "received";
    if (message.delivery_state == "pending") return "pending";
    if (message.delivery_state == "failed") return message.delivery_error.empty()
        ? "failed"
        : "failed: " + message.delivery_error;
    const auto readers = readers_for(conversation, message, current_user_id);
    if (readers.empty()) return "sent";
    const std::size_t peers = conversation.participant_user_ids.size() > 0
        ? conversation.participant_user_ids.size() - 1
        : 0;
    if (peers > 1 && readers.size() < peers) return "read by " + join_strings(readers, ",");
    if (peers > 1) return "read by all";
    return "read";
}

DesktopMessage message_from_synced(const std::string& conversation_id,
                                   const transport::SyncedMessage& source) {
    DesktopMessage message;
    message.conversation_id = conversation_id;
    message.message_id = source.message_id;
    message.sender_user_id = source.sender_user_id;
    message.text = source.text;
    message.created_at_ms = source.created_at_ms;
    message.edited = source.edited;
    message.deleted = source.deleted;
    message.delivery_state = "sent";
    message.attachment_id = source.attachment_id;
    message.filename = source.filename;
    message.mime_type = source.mime_type;
    message.size_bytes = source.size_bytes;
    message.reply_to_message_id = source.reply_to_message_id;
    message.forwarded_from_conversation_id = source.forwarded_from_conversation_id;
    message.forwarded_from_message_id = source.forwarded_from_message_id;
    message.forwarded_from_sender_user_id = source.forwarded_from_sender_user_id;
    message.reaction_summary = source.reaction_summary;
    message.pinned = source.pinned;
    return message;
}

DesktopMessage message_from_result(const std::string& conversation_id,
                                   const transport::MessageResult& source) {
    DesktopMessage message;
    message.conversation_id = conversation_id;
    message.message_id = source.message_id;
    message.sender_user_id = source.sender_user_id;
    message.text = source.text;
    message.created_at_ms = source.created_at_ms;
    message.delivery_state = "sent";
    message.attachment_id = source.attachment_id;
    message.filename = source.filename;
    message.mime_type = source.mime_type;
    message.size_bytes = source.size_bytes;
    message.preview_text = source.preview_text;
    message.reply_to_message_id = source.reply_to_message_id;
    message.forwarded_from_conversation_id = source.forwarded_from_conversation_id;
    message.forwarded_from_message_id = source.forwarded_from_message_id;
    message.forwarded_from_sender_user_id = source.forwarded_from_sender_user_id;
    message.reaction_summary = source.reaction_summary;
    message.pinned = source.pinned;
    return message;
}

}  // namespace

void DesktopChatStore::clear() {
    conversations_.clear();
    selected_conversation_id_.clear();
    local_message_counter_ = 0;
}

void DesktopChatStore::set_current_user(std::string user_id) {
    current_user_id_ = std::move(user_id);
}

void DesktopChatStore::set_selected_conversation(std::string conversation_id) {
    selected_conversation_id_ = std::move(conversation_id);
    if (!selected_conversation_id_.empty()) {
        ensure_conversation(selected_conversation_id_).unread_count = 0;
    }
}

void DesktopChatStore::apply_sync(const transport::SyncResult& sync) {
    conversations_.clear();
    for (const auto& source : sync.conversations) {
        DesktopConversation conversation;
        conversation.conversation_id = source.conversation_id;
        conversation.title = source.title;
        conversation.participant_user_ids = source.participant_user_ids;
        conversation.read_markers = source.read_markers;
        conversation.sync_version = source.version;
        conversation.history_next_before_message_id = source.next_before_message_id;
        conversation.history_has_more = source.has_more;
        for (const auto& message : source.messages) {
            conversation.messages.push_back(message_from_synced(source.conversation_id, message));
        }
        if (!conversation.messages.empty()) {
            conversation.last_message_id = conversation.messages.back().message_id;
        }
        conversations_.push_back(std::move(conversation));
    }
    if (selected_conversation_id_.empty() && !conversations_.empty()) {
        selected_conversation_id_ = conversations_.front().conversation_id;
    }
    if (!selected_conversation_id_.empty()) {
        ensure_conversation(selected_conversation_id_).unread_count = 0;
    }
}

void DesktopChatStore::apply_incremental_sync(const transport::SyncResult& sync) {
    for (const auto& source : sync.conversations) {
        auto& conversation = ensure_conversation(source.conversation_id);
        conversation.title = source.title;
        conversation.participant_user_ids = source.participant_user_ids;
        if (!source.read_markers.empty()) {
            conversation.read_markers = source.read_markers;
        }
        if (source.version > conversation.sync_version) {
            conversation.sync_version = source.version;
        }
        if (!source.next_before_message_id.empty() || source.has_more) {
            conversation.history_next_before_message_id = source.next_before_message_id;
            conversation.history_has_more = source.has_more;
        }
        for (const auto& message : source.messages) {
            upsert_message(message_from_synced(source.conversation_id, message), false);
        }
        for (const auto& change : source.changes) {
            if (change.kind == "message_edited") {
                apply_message_edited(source.conversation_id, change.message_id, change.text);
            } else if (change.kind == "message_deleted") {
                apply_message_deleted(source.conversation_id, change.message_id);
            } else if (change.kind == "read_marker") {
                apply_read_marker(source.conversation_id,
                                  change.reader_user_id,
                                  change.last_read_message_id);
            } else if (change.kind == "message_reaction_updated") {
                apply_reaction_summary(source.conversation_id,
                                       change.message_id,
                                       change.reaction_summary);
            } else if (change.kind == "message_pin_updated") {
                apply_pin_state(source.conversation_id,
                                change.message_id,
                                change.pinned);
            }
            if (change.version > conversation.sync_version) {
                conversation.sync_version = change.version;
            }
        }
    }
    if (selected_conversation_id_.empty() && !conversations_.empty()) {
        selected_conversation_id_ = conversations_.front().conversation_id;
    }
    if (!selected_conversation_id_.empty()) {
        ensure_conversation(selected_conversation_id_).unread_count = 0;
    }
}

void DesktopChatStore::apply_history_page(const transport::SyncResult& sync) {
    for (const auto& source : sync.conversations) {
        auto& conversation = ensure_conversation(source.conversation_id);
        conversation.title = source.title;
        conversation.participant_user_ids = source.participant_user_ids;
        if (!source.read_markers.empty()) {
            conversation.read_markers = source.read_markers;
        }
        if (source.version > conversation.sync_version) {
            conversation.sync_version = source.version;
        }
        conversation.history_next_before_message_id = source.next_before_message_id;
        conversation.history_has_more = source.has_more;
        for (auto it = source.messages.rbegin(); it != source.messages.rend(); ++it) {
            const auto exists = std::find_if(
                conversation.messages.begin(),
                conversation.messages.end(),
                [&](const auto& current) { return current.message_id == it->message_id; });
            if (exists != conversation.messages.end()) continue;
            conversation.messages.insert(conversation.messages.begin(),
                                         message_from_synced(source.conversation_id, *it));
        }
        if (conversation.last_message_id.empty() && !conversation.messages.empty()) {
            conversation.last_message_id = conversation.messages.back().message_id;
        }
    }
}

void DesktopChatStore::apply_sent_message(const std::string& conversation_id,
                                          const transport::MessageResult& message) {
    if (!message.ok) return;
    upsert_message(message_from_result(conversation_id, message), false);
}

std::string DesktopChatStore::add_pending_message(const std::string& conversation_id,
                                                  const std::string& text,
                                                  long long created_at_ms) {
    DesktopMessage message;
    message.conversation_id = conversation_id;
    message.message_id = "local_" + std::to_string(++local_message_counter_);
    message.sender_user_id = current_user_id_;
    message.text = text;
    message.created_at_ms = created_at_ms > 0 ? created_at_ms : now_ms();
    message.delivery_state = "pending";
    upsert_message(message, false);
    return message.message_id;
}

std::string DesktopChatStore::add_pending_attachment_message(const std::string& conversation_id,
                                                             const std::string& caption,
                                                             const std::string& filename,
                                                             const std::string& mime_type,
                                                             long long size_bytes,
                                                             long long created_at_ms) {
    DesktopMessage message;
    message.conversation_id = conversation_id;
    message.message_id = "local_" + std::to_string(++local_message_counter_);
    message.sender_user_id = current_user_id_;
    message.text = caption;
    message.created_at_ms = created_at_ms > 0 ? created_at_ms : now_ms();
    message.delivery_state = "pending";
    message.attachment_id = "pending";
    message.filename = filename;
    message.mime_type = mime_type;
    message.size_bytes = size_bytes;
    upsert_message(message, false);
    return message.message_id;
}

void DesktopChatStore::resolve_pending_message(const std::string& conversation_id,
                                               const std::string& local_message_id,
                                               const transport::MessageResult& message) {
    if (!message.ok) return;
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == local_message_id;
    });
    DesktopMessage resolved = message_from_result(conversation_id, message);
    if (it != conversation.messages.end()) {
        if (resolved.created_at_ms <= 0) resolved.created_at_ms = it->created_at_ms;
        const auto resolved_id = resolved.message_id;
        *it = std::move(resolved);
        conversation.last_message_id = resolved_id;
        return;
    }
    upsert_message(std::move(resolved), false);
}

void DesktopChatStore::fail_pending_message(const std::string& conversation_id,
                                            const std::string& local_message_id,
                                            const std::string& error) {
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == local_message_id;
    });
    if (it == conversation.messages.end()) return;
    it->delivery_state = "failed";
    it->delivery_error = error;
}

void DesktopChatStore::apply_push(const std::string& type, const std::string& envelope_json) {
    const std::string conversation_id = extract_payload_string(envelope_json, "conversation_id");
    if (conversation_id.empty()) return;

    if (type == "message_deliver") {
        DesktopMessage message;
        message.conversation_id = conversation_id;
        message.message_id = extract_payload_string(envelope_json, "message_id");
        message.sender_user_id = extract_payload_string(envelope_json, "sender_user_id");
        message.text = extract_payload_string(envelope_json, "text");
        message.created_at_ms = extract_payload_number(envelope_json, "created_at_ms");
        message.delivery_state = "sent";
        message.attachment_id = extract_payload_string(envelope_json, "attachment_id");
        message.filename = extract_payload_string(envelope_json, "filename");
        message.mime_type = extract_payload_string(envelope_json, "mime_type");
        message.size_bytes = static_cast<long long>(extract_payload_size(envelope_json, "size_bytes"));
        message.reply_to_message_id = extract_payload_string(envelope_json, "reply_to_message_id");
        message.forwarded_from_conversation_id = extract_payload_string(envelope_json, "forwarded_from_conversation_id");
        message.forwarded_from_message_id = extract_payload_string(envelope_json, "forwarded_from_message_id");
        message.forwarded_from_sender_user_id = extract_payload_string(envelope_json, "forwarded_from_sender_user_id");
        const bool unread = message.sender_user_id != current_user_id_
                         && conversation_id != selected_conversation_id_;
        upsert_message(std::move(message), unread);
        return;
    }

    if (type == "message_edited") {
        apply_message_edited(conversation_id,
                             extract_payload_string(envelope_json, "message_id"),
                             extract_payload_string(envelope_json, "text"));
        return;
    }

    if (type == "message_deleted") {
        apply_message_deleted(conversation_id,
                              extract_payload_string(envelope_json, "message_id"));
        return;
    }

    if (type == "message_read_update") {
        apply_read_marker(conversation_id,
                          extract_payload_string(envelope_json, "reader_user_id"),
                          extract_payload_string(envelope_json, "last_read_message_id"));
        return;
    }

    if (type == "message_reaction_updated") {
        apply_reaction_summary(conversation_id,
                               extract_payload_string(envelope_json, "message_id"),
                               extract_payload_string(envelope_json, "reaction_summary"));
        return;
    }

    if (type == "message_pin_updated") {
        JsonParser parser(envelope_json);
        JsonValue root;
        bool pinned = false;
        if (parser.parse(root) && root.is_object()) {
            const auto* payload = find_member(*root.as_object(), "payload");
            if (payload && payload->is_object()) {
                pinned = extract_bool(*payload->as_object(), "pinned");
            }
        }
        apply_pin_state(conversation_id,
                        extract_payload_string(envelope_json, "message_id"),
                        pinned);
    }
}

const std::string& DesktopChatStore::selected_conversation_id() const noexcept {
    return selected_conversation_id_;
}

const DesktopConversation* DesktopChatStore::selected_conversation() const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == selected_conversation_id_;
    });
    return it == conversations_.end() ? nullptr : &*it;
}

std::vector<DesktopConversation> DesktopChatStore::conversations() const {
    return conversations_;
}

std::vector<DesktopConversation> DesktopChatStore::filtered_conversations(const std::string& query) const {
    if (query.empty()) return conversations_;
    std::vector<DesktopConversation> matches;
    for (const auto& conversation : conversations_) {
        bool matched = contains_case_insensitive(conversation.conversation_id, query)
                    || contains_case_insensitive(conversation.title, query);
        for (const auto& user_id : conversation.participant_user_ids) {
            matched = matched || contains_case_insensitive(user_id, query);
        }
        for (const auto& message : conversation.messages) {
            matched = matched || message_matches_query(message, query);
        }
        if (matched) matches.push_back(conversation);
    }
    return matches;
}

std::vector<DesktopMessageSearchResult> DesktopChatStore::search_selected_messages(const std::string& query) const {
    std::vector<DesktopMessageSearchResult> results;
    if (query.empty()) return results;
    const auto* conversation = selected_conversation();
    if (conversation == nullptr) return results;
    for (std::size_t i = 0; i < conversation->messages.size(); ++i) {
        const auto& message = conversation->messages[i];
        if (!message_matches_query(message, query)) continue;
        results.push_back(DesktopMessageSearchResult {
            .index = i,
            .message_id = message.message_id,
            .sender_user_id = message.sender_user_id,
            .snippet = message_search_snippet(message),
            .created_at_ms = message.created_at_ms,
        });
    }
    return results;
}

std::string DesktopChatStore::render_selected_transcript() const {
    const auto* conversation = selected_conversation();
    if (conversation == nullptr) return {};

    std::ostringstream out;
    out << "# " << conversation->conversation_id;
    if (!conversation->title.empty()) out << " (" << conversation->title << ")";
    out << "\n";

    const std::size_t tail = conversation->messages.size() > 100 ? conversation->messages.size() - 100 : 0;
    for (std::size_t i = tail; i < conversation->messages.size(); ++i) {
        const auto& message = conversation->messages[i];
        const bool outgoing = message.sender_user_id == current_user_id_;
        out << (outgoing ? ">>" : "<<") << " [" << format_time(message.created_at_ms) << "] "
            << message.sender_user_id << " | " << status_label(*conversation, message, current_user_id_)
            << " | " << message.message_id << "\n";
        out << "   " << (message.deleted ? std::string("<deleted>") : message.text);
        if (message.edited) out << " (edited)";
        if (message.pinned) out << "\n   [pinned]";
        if (!message.reply_to_message_id.empty()) out << "\n   [reply_to=" << message.reply_to_message_id << "]";
        if (!message.forwarded_from_message_id.empty()) {
            out << "\n   [forwarded_from=" << message.forwarded_from_conversation_id
                << "/" << message.forwarded_from_message_id
                << " sender=" << message.forwarded_from_sender_user_id << "]";
        }
        if (!message.reaction_summary.empty()) out << "\n   [reactions=" << message.reaction_summary << "]";
        if (!message.attachment_id.empty()) {
            out << "\n   [attach=" << message.attachment_id;
            if (!message.filename.empty()) out << " file=" << message.filename;
            if (!message.mime_type.empty()) out << " mime=" << message.mime_type;
            if (message.size_bytes > 0) out << " bytes=" << message.size_bytes;
            out << preview_label(message);
            out << "]";
        }
        out << "\n";
    }
    return out.str();
}

std::string DesktopChatStore::render_selected_timeline_html(const std::string& search_query,
                                                            const std::string& focused_message_id) const {
    const auto* conversation = selected_conversation();
    if (conversation == nullptr) return {};

    std::ostringstream out;
    out << "<html><head><style>"
        << "body{background:#f3efe6;font-family:'Segoe UI',sans-serif;margin:12px;color:#1e2a28;}"
        << ".title{font-weight:700;margin:0 0 12px 0;color:#38524a;}"
        << ".row{clear:both;margin:8px 0;overflow:auto;}"
        << ".bubble{max-width:72%;padding:8px 10px;border-radius:14px;box-shadow:0 1px 2px rgba(0,0,0,.10);}"
        << ".out .bubble{float:right;background:#d7f3c9;border-bottom-right-radius:4px;}"
        << ".in .bubble{float:left;background:#ffffff;border-bottom-left-radius:4px;}"
        << ".meta{font-size:11px;color:#6d7b78;margin-bottom:4px;}"
        << ".text{font-size:14px;line-height:1.35;}"
        << ".attach{font-size:12px;margin-top:6px;color:#44635c;background:rgba(255,255,255,.45);padding:4px;border-radius:6px;}"
        << ".failed .bubble{background:#ffd7cf;}"
        << ".pending .meta{color:#9a7a28;}"
        << ".match .bubble{border:2px solid #d69d22;}"
        << ".focused .bubble{border:3px solid #315c9c;}"
        << "</style></head><body>";
    out << "<div class='title'>" << html_escape(conversation->conversation_id);
    if (!conversation->title.empty()) out << " - " << html_escape(conversation->title);
    out << "</div>";

    const std::size_t tail = conversation->messages.size() > 100 ? conversation->messages.size() - 100 : 0;
    for (std::size_t i = tail; i < conversation->messages.size(); ++i) {
        const auto& message = conversation->messages[i];
        const bool outgoing = message.sender_user_id == current_user_id_;
        const auto status = status_label(*conversation, message, current_user_id_);
        out << "<div class='row " << (outgoing ? "out" : "in");
        if (message.delivery_state == "pending") out << " pending";
        if (message.delivery_state == "failed") out << " failed";
        if (!search_query.empty() && message_matches_query(message, search_query)) out << " match";
        if (!focused_message_id.empty() && message.message_id == focused_message_id) out << " focused";
        out << "'><div class='bubble'>";
        out << "<div class='meta'>" << html_escape(format_time(message.created_at_ms))
            << " · " << html_escape(message.sender_user_id)
            << " · " << html_escape(status)
            << " · <a href='msg://" << html_escape(message.message_id) << "'>"
            << html_escape(message.message_id) << "</a></div>";
        out << "<div class='text'>" << html_escape(message.deleted ? std::string("<deleted>") : message.text);
        if (message.edited) out << " <span class='meta'>(edited)</span>";
        out << "</div>";
        if (message.pinned || !message.reply_to_message_id.empty()
            || !message.forwarded_from_message_id.empty() || !message.reaction_summary.empty()) {
            out << "<div class='attach'>";
            if (message.pinned) out << "pinned ";
            if (!message.reply_to_message_id.empty()) out << "reply_to=" << html_escape(message.reply_to_message_id) << " ";
            if (!message.forwarded_from_message_id.empty()) {
                out << "forwarded_from=" << html_escape(message.forwarded_from_conversation_id)
                    << "/" << html_escape(message.forwarded_from_message_id) << " ";
            }
            if (!message.reaction_summary.empty()) out << "reactions=" << html_escape(message.reaction_summary);
            out << "</div>";
        }
        if (!message.attachment_id.empty()) {
            out << "<div class='attach'>attach=" << html_escape(message.attachment_id);
            if (!message.filename.empty()) out << " file=" << html_escape(message.filename);
            if (!message.mime_type.empty()) out << " mime=" << html_escape(message.mime_type);
            if (message.size_bytes > 0) out << " bytes=" << message.size_bytes;
            out << html_escape(preview_label(message)) << "</div>";
        }
        out << "</div></div>";
    }
    out << "</body></html>";
    return out.str();
}

std::string DesktopChatStore::render_conversation_summary() const {
    std::ostringstream out;
    for (const auto& conversation : conversations_) {
        out << conversation.conversation_id;
        if (!conversation.title.empty()) out << " (" << conversation.title << ")";
        if (conversation.unread_count > 0) out << " unread=" << conversation.unread_count;
        if (!conversation.last_message_id.empty()) out << " cursor=" << conversation.last_message_id;
        if (conversation.sync_version > 0) out << " version=" << conversation.sync_version;
        out << "\n";
    }
    return out.str();
}

std::string DesktopChatStore::last_message_id(const std::string& conversation_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    return it == conversations_.end() ? std::string {} : it->last_message_id;
}

std::string DesktopChatStore::history_next_before_message_id(const std::string& conversation_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    return it == conversations_.end() ? std::string {} : it->history_next_before_message_id;
}

bool DesktopChatStore::history_has_more(const std::string& conversation_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    return it != conversations_.end() && it->history_has_more;
}

std::string DesktopChatStore::latest_attachment_id(const std::string& conversation_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    if (it == conversations_.end()) return {};
    for (auto message = it->messages.rbegin(); message != it->messages.rend(); ++message) {
        if (!message->attachment_id.empty()) return message->attachment_id;
    }
    return {};
}

std::string DesktopChatStore::latest_attachment_filename(const std::string& conversation_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    if (it == conversations_.end()) return {};
    for (auto message = it->messages.rbegin(); message != it->messages.rend(); ++message) {
        if (!message->attachment_id.empty() && !message->filename.empty()) return message->filename;
    }
    return {};
}

std::string DesktopChatStore::attachment_filename(const std::string& conversation_id,
                                                  const std::string& attachment_id) const {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    if (it == conversations_.end()) return {};
    for (auto message = it->messages.rbegin(); message != it->messages.rend(); ++message) {
        if (message->attachment_id == attachment_id && !message->filename.empty()) {
            return message->filename;
        }
    }
    return {};
}

std::vector<transport::SyncCursor> DesktopChatStore::sync_cursors() const {
    std::vector<transport::SyncCursor> cursors;
    for (const auto& conversation : conversations_) {
        if (!conversation.conversation_id.empty()) {
            cursors.push_back(transport::SyncCursor {
                .conversation_id = conversation.conversation_id,
                .last_message_id = conversation.last_message_id,
                .version = conversation.sync_version,
            });
        }
    }
    return cursors;
}

bool DesktopChatStore::save_to_file(const std::string& path, std::string* error) const {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) {
        if (error) *error = "open_for_write_failed";
        return false;
    }

    out << "{";
    out << "\"version\":1,";
    out << "\"current_user_id\":";
    write_string(out, current_user_id_);
    out << ",\"selected_conversation_id\":";
    write_string(out, selected_conversation_id_);
    out << ",\"conversations\":[";
    for (std::size_t ci = 0; ci < conversations_.size(); ++ci) {
        const auto& conversation = conversations_[ci];
        if (ci > 0) out << ",";
        out << "{";
        out << "\"conversation_id\":";
        write_string(out, conversation.conversation_id);
        out << ",\"title\":";
        write_string(out, conversation.title);
        out << ",\"unread_count\":" << conversation.unread_count;
        out << ",\"last_message_id\":";
        write_string(out, conversation.last_message_id);
        out << ",\"sync_version\":" << conversation.sync_version;
        out << ",\"history_next_before_message_id\":";
        write_string(out, conversation.history_next_before_message_id);
        out << ",\"history_has_more\":" << (conversation.history_has_more ? "true" : "false");
        out << ",\"read_markers\":{";
        for (std::size_t ri = 0; ri < conversation.read_markers.size(); ++ri) {
            if (ri > 0) out << ",";
            write_string(out, conversation.read_markers[ri].user_id);
            out << ":";
            write_string(out, conversation.read_markers[ri].last_read_message_id);
        }
        out << "}";
        out << ",\"participant_user_ids\":[";
        for (std::size_t pi = 0; pi < conversation.participant_user_ids.size(); ++pi) {
            if (pi > 0) out << ",";
            write_string(out, conversation.participant_user_ids[pi]);
        }
        out << "],\"messages\":[";
        for (std::size_t mi = 0; mi < conversation.messages.size(); ++mi) {
            const auto& message = conversation.messages[mi];
            if (mi > 0) out << ",";
            out << "{";
            out << "\"message_id\":";
            write_string(out, message.message_id);
            out << ",\"conversation_id\":";
            write_string(out, message.conversation_id);
            out << ",\"sender_user_id\":";
            write_string(out, message.sender_user_id);
            out << ",\"text\":";
            write_string(out, message.text);
            out << ",\"created_at_ms\":" << message.created_at_ms;
            out << ",\"edited\":" << (message.edited ? "true" : "false");
            out << ",\"deleted\":" << (message.deleted ? "true" : "false");
            out << ",\"delivery_state\":";
            write_string(out, message.delivery_state);
            out << ",\"delivery_error\":";
            write_string(out, message.delivery_error);
            out << ",\"attachment_id\":";
            write_string(out, message.attachment_id);
            out << ",\"filename\":";
            write_string(out, message.filename);
            out << ",\"mime_type\":";
            write_string(out, message.mime_type);
            out << ",\"size_bytes\":" << message.size_bytes;
            out << ",\"preview_text\":";
            write_string(out, message.preview_text);
            out << ",\"reply_to_message_id\":";
            write_string(out, message.reply_to_message_id);
            out << ",\"forwarded_from_conversation_id\":";
            write_string(out, message.forwarded_from_conversation_id);
            out << ",\"forwarded_from_message_id\":";
            write_string(out, message.forwarded_from_message_id);
            out << ",\"forwarded_from_sender_user_id\":";
            write_string(out, message.forwarded_from_sender_user_id);
            out << ",\"reaction_summary\":";
            write_string(out, message.reaction_summary);
            out << ",\"pinned\":" << (message.pinned ? "true" : "false");
            out << "}";
        }
        out << "]}";
    }
    out << "]}";
    if (!out) {
        if (error) *error = "write_failed";
        return false;
    }
    return true;
}

bool DesktopChatStore::load_from_file(const std::string& path, std::string* error) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        if (error) *error = "open_for_read_failed";
        return false;
    }
    std::ostringstream buffer;
    buffer << in.rdbuf();

    const std::string json = buffer.str();
    JsonParser parser(json);
    JsonValue root;
    if (!parser.parse(root) || !root.is_object()) {
        if (error) *error = "invalid_json";
        return false;
    }

    const auto& object = *root.as_object();
    std::vector<DesktopConversation> loaded;
    const auto* conversations = find_member(object, "conversations");
    if (conversations && conversations->is_array()) {
        for (const auto& conv_value : *conversations->as_array()) {
            if (!conv_value.is_object()) continue;
            const auto& conv_object = *conv_value.as_object();
            DesktopConversation conversation;
            conversation.conversation_id = string_or_empty(conv_object, "conversation_id");
            if (conversation.conversation_id.empty()) continue;
            conversation.title = string_or_empty(conv_object, "title");
            conversation.unread_count = extract_size(conv_object, "unread_count");
            conversation.last_message_id = string_or_empty(conv_object, "last_message_id");
            conversation.sync_version = static_cast<int>(extract_size(conv_object, "sync_version"));
            conversation.history_next_before_message_id = string_or_empty(conv_object, "history_next_before_message_id");
            conversation.history_has_more = extract_bool(conv_object, "history_has_more");
            const auto* markers = find_member(conv_object, "read_markers");
            if (markers && markers->is_object()) {
                for (const auto& [user_id, marker_value] : *markers->as_object()) {
                    if (marker_value.is_string()) {
                        conversation.read_markers.push_back(transport::ReadMarker {
                            .user_id = user_id,
                            .last_read_message_id = *marker_value.as_string(),
                        });
                    }
                }
            }

            const auto* participants = find_member(conv_object, "participant_user_ids");
            if (participants && participants->is_array()) {
                for (const auto& participant : *participants->as_array()) {
                    if (participant.is_string()) conversation.participant_user_ids.push_back(*participant.as_string());
                }
            }

            const auto* messages = find_member(conv_object, "messages");
            if (messages && messages->is_array()) {
                for (const auto& msg_value : *messages->as_array()) {
                    if (!msg_value.is_object()) continue;
                    const auto& msg_object = *msg_value.as_object();
                    DesktopMessage message;
                    message.message_id = string_or_empty(msg_object, "message_id");
                    if (message.message_id.empty()) continue;
                    message.conversation_id = string_or_empty(msg_object, "conversation_id");
                    if (message.conversation_id.empty()) message.conversation_id = conversation.conversation_id;
                    message.sender_user_id = string_or_empty(msg_object, "sender_user_id");
                    message.text = string_or_empty(msg_object, "text");
                    message.created_at_ms = extract_number(msg_object, "created_at_ms");
                    message.edited = extract_bool(msg_object, "edited");
                    message.deleted = extract_bool(msg_object, "deleted");
                    message.delivery_state = string_or_empty(msg_object, "delivery_state");
                    message.delivery_error = string_or_empty(msg_object, "delivery_error");
                    message.attachment_id = string_or_empty(msg_object, "attachment_id");
                    message.filename = string_or_empty(msg_object, "filename");
                    message.mime_type = string_or_empty(msg_object, "mime_type");
                    message.size_bytes = static_cast<long long>(extract_size(msg_object, "size_bytes"));
                    message.preview_text = string_or_empty(msg_object, "preview_text");
                    message.reply_to_message_id = string_or_empty(msg_object, "reply_to_message_id");
                    message.forwarded_from_conversation_id = string_or_empty(msg_object, "forwarded_from_conversation_id");
                    message.forwarded_from_message_id = string_or_empty(msg_object, "forwarded_from_message_id");
                    message.forwarded_from_sender_user_id = string_or_empty(msg_object, "forwarded_from_sender_user_id");
                    message.reaction_summary = string_or_empty(msg_object, "reaction_summary");
                    message.pinned = extract_bool(msg_object, "pinned");
                    conversation.messages.push_back(std::move(message));
                }
            }
            if (conversation.last_message_id.empty() && !conversation.messages.empty()) {
                conversation.last_message_id = conversation.messages.back().message_id;
            }
            loaded.push_back(std::move(conversation));
        }
    }

    conversations_ = std::move(loaded);
    current_user_id_ = string_or_empty(object, "current_user_id");
    selected_conversation_id_ = string_or_empty(object, "selected_conversation_id");
    if (selected_conversation_id_.empty() && !conversations_.empty()) {
        selected_conversation_id_ = conversations_.front().conversation_id;
    }
    return true;
}

DesktopConversation& DesktopChatStore::ensure_conversation(const std::string& conversation_id) {
    auto it = std::find_if(conversations_.begin(), conversations_.end(), [&](const auto& c) {
        return c.conversation_id == conversation_id;
    });
    if (it != conversations_.end()) return *it;

    DesktopConversation conversation;
    conversation.conversation_id = conversation_id;
    conversations_.push_back(std::move(conversation));
    return conversations_.back();
}

void DesktopChatStore::upsert_message(DesktopMessage message, bool count_unread) {
    auto& conversation = ensure_conversation(message.conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == message.message_id;
    });
    if (it == conversation.messages.end()) {
        conversation.messages.push_back(std::move(message));
        if (conversation.messages.back().message_id.rfind("local_", 0) != 0) {
            conversation.last_message_id = conversation.messages.back().message_id;
        }
        if (count_unread) ++conversation.unread_count;
    } else {
        *it = std::move(message);
        if (!conversation.messages.empty()) {
            const auto& last_id = conversation.messages.back().message_id;
            if (last_id.rfind("local_", 0) != 0) conversation.last_message_id = last_id;
        }
    }
}

void DesktopChatStore::apply_message_deleted(const std::string& conversation_id,
                                             const std::string& message_id) {
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == message_id;
    });
    if (it != conversation.messages.end()) {
        it->deleted = true;
        it->text.clear();
    }
}

void DesktopChatStore::apply_message_edited(const std::string& conversation_id,
                                            const std::string& message_id,
                                            const std::string& text) {
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == message_id;
    });
    if (it != conversation.messages.end()) {
        it->text = text;
        it->edited = true;
    }
}

void DesktopChatStore::apply_read_marker(const std::string& conversation_id,
                                         const std::string& reader_user_id,
                                         const std::string& last_read_message_id) {
    if (reader_user_id.empty() || last_read_message_id.empty()) return;
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.read_markers.begin(), conversation.read_markers.end(),
                           [&](const auto& marker) { return marker.user_id == reader_user_id; });
    if (it == conversation.read_markers.end()) {
        conversation.read_markers.push_back(transport::ReadMarker {
            .user_id = reader_user_id,
            .last_read_message_id = last_read_message_id,
        });
    } else {
        it->last_read_message_id = last_read_message_id;
    }
}

void DesktopChatStore::apply_reaction_summary(const std::string& conversation_id,
                                              const std::string& message_id,
                                              const std::string& reaction_summary) {
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == message_id;
    });
    if (it != conversation.messages.end()) {
        it->reaction_summary = reaction_summary;
    }
}

void DesktopChatStore::apply_pin_state(const std::string& conversation_id,
                                       const std::string& message_id,
                                       bool pinned) {
    auto& conversation = ensure_conversation(conversation_id);
    auto it = std::find_if(conversation.messages.begin(), conversation.messages.end(), [&](const auto& m) {
        return m.message_id == message_id;
    });
    if (it != conversation.messages.end()) {
        it->pinned = pinned;
    }
}

}  // namespace telegram_like::client::app_desktop
