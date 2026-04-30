#pragma once

#include "transport/control_plane_client.h"

#include <cstddef>
#include <string>
#include <vector>

namespace telegram_like::client::app_desktop {

struct DesktopMessage {
    std::string message_id;
    std::string conversation_id;
    std::string sender_user_id;
    std::string text;
    long long created_at_ms {0};
    bool edited {false};
    bool deleted {false};
    std::string delivery_state;
    std::string delivery_error;
    std::string attachment_id;
    std::string filename;
    std::string mime_type;
    long long size_bytes {0};
    std::string preview_text;
    std::string reply_to_message_id;
    std::string forwarded_from_conversation_id;
    std::string forwarded_from_message_id;
    std::string forwarded_from_sender_user_id;
    std::string reaction_summary;
    bool pinned {false};
};

struct DesktopConversation {
    std::string conversation_id;
    std::string title;
    std::vector<std::string> participant_user_ids;
    std::vector<transport::ReadMarker> read_markers;
    std::vector<DesktopMessage> messages;
    std::size_t unread_count {0};
    std::string last_message_id;
    int sync_version {0};
    std::string history_next_before_message_id;
    bool history_has_more {false};
};

struct DesktopMessageSearchResult {
    std::size_t index {0};
    std::string message_id;
    std::string sender_user_id;
    std::string snippet;
    long long created_at_ms {0};
};

// M137: bubble palette passed into render_selected_timeline_html so the
// renderer stays Qt-free (chat_client_core has no Qt link) while the
// caller (app_desktop main.cpp) can inject light/dark theme colors from
// design::active_theme(). Defaults intentionally retain the M125 light
// palette so existing call sites + the store_test smoke compile unchanged.
struct DesktopBubblePalette {
    const char* chat_area_bg     = "#e6ebee";
    const char* own_bubble       = "#3390ec";
    const char* own_bubble_text  = "#ffffff";
    const char* peer_bubble      = "#ffffff";
    const char* peer_bubble_text = "#0f1419";
    const char* primary          = "#3390ec";
    const char* text_muted       = "#7c8a96";
    const char* tick_sent        = "#a8c8ec";
    const char* tick_read        = "#3390ec";
    const char* failed_bubble    = "#ffd7cf";
};

class DesktopChatStore {
public:
    void clear();
    void set_current_user(std::string user_id);
    [[nodiscard]] const std::string& current_user_id() const { return current_user_id_; }
    void set_selected_conversation(std::string conversation_id);

    void apply_sync(const transport::SyncResult& sync);
    void apply_incremental_sync(const transport::SyncResult& sync);
    void apply_history_page(const transport::SyncResult& sync);
    void apply_sent_message(const std::string& conversation_id,
                            const transport::MessageResult& message);
    [[nodiscard]] std::string add_pending_message(const std::string& conversation_id,
                                                  const std::string& text,
                                                  long long created_at_ms = 0);
    [[nodiscard]] std::string add_pending_attachment_message(const std::string& conversation_id,
                                                             const std::string& caption,
                                                             const std::string& filename,
                                                             const std::string& mime_type,
                                                             long long size_bytes,
                                                             long long created_at_ms = 0);
    void resolve_pending_message(const std::string& conversation_id,
                                 const std::string& local_message_id,
                                 const transport::MessageResult& message);
    void fail_pending_message(const std::string& conversation_id,
                              const std::string& local_message_id,
                              const std::string& error);
    void apply_push(const std::string& type, const std::string& envelope_json);
    void apply_reaction_summary(const std::string& conversation_id,
                                const std::string& message_id,
                                const std::string& reaction_summary);
    void apply_pin_state(const std::string& conversation_id,
                         const std::string& message_id,
                         bool pinned);
    void apply_message_edited(const std::string& conversation_id,
                              const std::string& message_id,
                              const std::string& text);
    void apply_message_deleted(const std::string& conversation_id,
                               const std::string& message_id);

    [[nodiscard]] const std::string& selected_conversation_id() const noexcept;
    [[nodiscard]] const DesktopConversation* selected_conversation() const;
    [[nodiscard]] std::vector<DesktopConversation> conversations() const;
    [[nodiscard]] std::vector<DesktopConversation> filtered_conversations(const std::string& query) const;
    [[nodiscard]] std::vector<DesktopMessageSearchResult> search_selected_messages(const std::string& query) const;
    [[nodiscard]] std::string render_selected_transcript() const;
    [[nodiscard]] std::string render_selected_timeline_html(const std::string& search_query = {},
                                                            const std::string& focused_message_id = {},
                                                            const DesktopBubblePalette& palette = {}) const;
    [[nodiscard]] std::string render_conversation_summary() const;
    // M137: returns one of "pending"|"failed"|"sent"|"read"|"received" so the
    // mobile QML bridge (which has no access to the file-local status_label
    // helper in desktop_chat_store.cpp) can pick the right tick character.
    // Empty string = unknown conversation/message.
    [[nodiscard]] std::string delivery_tick(const std::string& conversation_id,
                                            const std::string& message_id) const;
    [[nodiscard]] std::string last_message_id(const std::string& conversation_id) const;
    [[nodiscard]] std::string history_next_before_message_id(const std::string& conversation_id) const;
    [[nodiscard]] bool history_has_more(const std::string& conversation_id) const;
    [[nodiscard]] std::string latest_attachment_id(const std::string& conversation_id) const;
    [[nodiscard]] std::string latest_attachment_filename(const std::string& conversation_id) const;
    [[nodiscard]] std::string attachment_filename(const std::string& conversation_id,
                                                  const std::string& attachment_id) const;
    [[nodiscard]] std::vector<transport::SyncCursor> sync_cursors() const;
    [[nodiscard]] bool save_to_file(const std::string& path, std::string* error = nullptr) const;
    [[nodiscard]] bool load_from_file(const std::string& path, std::string* error = nullptr);

private:
    [[nodiscard]] DesktopConversation& ensure_conversation(const std::string& conversation_id);
    void upsert_message(DesktopMessage message, bool count_unread);
    void apply_read_marker(const std::string& conversation_id,
                           const std::string& reader_user_id,
                           const std::string& last_read_message_id);

    std::string current_user_id_;
    std::string selected_conversation_id_;
    int local_message_counter_ {0};
    std::vector<DesktopConversation> conversations_;
};

}  // namespace telegram_like::client::app_desktop
