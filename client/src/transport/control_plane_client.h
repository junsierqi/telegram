#pragma once

// High-level typed control-plane client.
//
// Wraps TcpLineClient with one-method-per-RPC ergonomics. Every request
// gets a fresh client-side correlation_id ("rpc_<n>") and blocks on the
// matching response. Unsolicited server pushes (correlation_id starts
// with "push_") are delivered out-of-band to an application callback.
//
// Parsing of response bodies is deliberately narrow — we only extract
// the fields the chat demo needs. Higher layers can parse the raw JSON
// line directly if they need more.

#include "net/tcp_line_client.h"

#include <atomic>
#include <functional>
#include <mutex>
#include <optional>
#include <utility>
#include <string>
#include <thread>
#include <vector>

namespace telegram_like::client::transport {

struct LoginResult {
    bool ok {false};
    std::string session_id;
    std::string user_id;
    std::string display_name;
    std::string device_id;
    std::string error_code;
    std::string error_message;
};

using RegisterResult = LoginResult;

struct ProfileResult {
    bool ok {false};
    std::string user_id;
    std::string username;
    std::string display_name;
    std::string error_code;
    std::string error_message;
};

struct UserSearchEntry {
    std::string user_id;
    std::string username;
    std::string display_name;
    bool online {false};
    bool is_contact {false};
};

struct UserSearchResult {
    bool ok {false};
    std::vector<UserSearchEntry> results;
    std::string error_code;
    std::string error_message;
};

struct MessageSearchEntry {
    std::string conversation_id;
    std::string conversation_title;
    std::string message_id;
    std::string sender_user_id;
    std::string text;
    long long created_at_ms {0};
    std::string attachment_id;
    std::string filename;
    std::string snippet;
};

struct MessageSearchResult {
    bool ok {false};
    std::vector<MessageSearchEntry> results;
    int next_offset {0};
    bool has_more {false};
    std::string error_code;
    std::string error_message;
};

struct MessageResult {
    bool ok {false};
    std::string message_id;
    std::string text;
    std::string sender_user_id;
    long long created_at_ms {0};
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
    std::string error_code;
    std::string error_message;
};

struct MessageReactionResult {
    bool ok {false};
    std::string conversation_id;
    std::string message_id;
    std::string actor_user_id;
    std::string emoji;
    std::string reaction_summary;
    std::string error_code;
    std::string error_message;
};

struct MessagePinResult {
    bool ok {false};
    std::string conversation_id;
    std::string message_id;
    std::string actor_user_id;
    bool pinned {false};
    std::string error_code;
    std::string error_message;
};

struct AttachmentFetchResult {
    bool ok {false};
    std::string attachment_id;
    std::string conversation_id;
    std::string uploader_user_id;
    std::string filename;
    std::string mime_type;
    long long size_bytes {0};
    std::string content;
    std::string error_code;
    std::string error_message;
};

struct DeviceEntry {
    std::string device_id;
    std::string label;
    std::string platform;
    bool trusted {false};
    bool active {false};
};

struct DeviceListResult {
    bool ok {false};
    std::vector<DeviceEntry> devices;
    std::string error_code;
    std::string error_message;
};

struct SyncedMessage {
    std::string message_id;
    std::string sender_user_id;
    std::string text;
    long long created_at_ms {0};
    bool edited {false};
    bool deleted {false};
    std::string attachment_id;
    std::string filename;
    std::string mime_type;
    long long size_bytes {0};
    std::string reply_to_message_id;
    std::string forwarded_from_conversation_id;
    std::string forwarded_from_message_id;
    std::string forwarded_from_sender_user_id;
    std::string reaction_summary;
    bool pinned {false};
};

struct ReadMarker {
    std::string user_id;
    std::string last_read_message_id;
};

struct SyncedChange {
    int version {0};
    std::string kind;
    std::string message_id;
    std::string sender_user_id;
    std::string text;
    std::string reader_user_id;
    std::string last_read_message_id;
    std::string reply_to_message_id;
    std::string forwarded_from_conversation_id;
    std::string forwarded_from_message_id;
    std::string forwarded_from_sender_user_id;
    std::string reaction_summary;
    bool pinned {false};
};

struct SyncedConversation {
    std::string conversation_id;
    std::string title;
    std::vector<std::string> participant_user_ids;
    std::vector<SyncedMessage> messages;
    std::vector<ReadMarker> read_markers;
    int version {0};
    std::vector<SyncedChange> changes;
    std::string next_before_message_id;
    bool has_more {false};
};

struct SyncResult {
    bool ok {false};
    std::vector<SyncedConversation> conversations;
    std::string error_code;
    std::string error_message;
};

struct ConversationActionResult {
    bool ok {false};
    SyncedConversation conversation;
    std::string error_code;
    std::string error_message;
};

struct SyncCursor {
    std::string conversation_id;
    std::string last_message_id;
    int version {0};
};

struct ContactEntry {
    std::string user_id;
    std::string display_name;
    bool online {false};
};

struct ContactListResult {
    bool ok {false};
    std::vector<ContactEntry> contacts;
    std::string error_code;
    std::string error_message;
};

struct PresenceUser {
    std::string user_id;
    bool online {false};
    long long last_seen_at_ms {0};
};

struct PresenceResult {
    bool ok {false};
    std::vector<PresenceUser> users;
    std::string error_code;
    std::string error_message;
};

struct AckResult {
    bool ok {false};
    std::string error_code;
    std::string error_message;
};

struct RemoteSessionStateResult {
    bool ok {false};
    std::string remote_session_id;
    std::string state;
    std::string target_user_id;
    std::string target_device_id;
    std::string error_code;
    std::string error_message;
};

struct RemoteRelayAssignmentResult {
    bool ok {false};
    std::string remote_session_id;
    std::string state;
    std::string relay_region;
    std::string relay_endpoint;
    std::string error_code;
    std::string error_message;
};

struct RemoteSessionTerminatedResult {
    bool ok {false};
    std::string remote_session_id;
    std::string state;
    std::string detail;
    std::string error_code;
    std::string error_message;
};

struct RemoteRendezvousCandidate {
    std::string kind;
    std::string address;
    int port {0};
    int priority {0};
};

// M122: voice/video call state result returned from CALL_INVITE/ACCEPT/
// DECLINE/END dispatch arms (server replies with CALL_STATE either way).
struct CallStateResult {
    bool ok {false};
    std::string call_id;
    std::string state;        // ringing | accepted | declined | ended | canceled
    std::string kind;         // audio | video (only set on the invite reply)
    std::string detail;
    std::string error_code;
    std::string error_message;
};

struct RemoteRendezvousResult {
    bool ok {false};
    std::string remote_session_id;
    std::string state;
    std::vector<RemoteRendezvousCandidate> candidates;
    std::string relay_region;
    std::string relay_endpoint;
    // M106 / D9: per-session AES-256-GCM key (base64). Empty when the server
    // is on a pre-M106 build or the session was created without a key.
    std::string relay_key_b64;
    std::string error_code;
    std::string error_message;
};

struct RemoteInputAckResult {
    bool ok {false};
    std::string remote_session_id;
    int sequence {0};
    std::string kind;
    std::string error_code;
    std::string error_message;
};

class ControlPlaneClient {
public:
    using PushHandler = std::function<void(const std::string& type, const std::string& envelope_json)>;

    ControlPlaneClient();
    ~ControlPlaneClient();

    ControlPlaneClient(const ControlPlaneClient&) = delete;
    ControlPlaneClient& operator=(const ControlPlaneClient&) = delete;

    [[nodiscard]] bool connect(const std::string& host, unsigned short port);
    [[nodiscard]] bool connect_tls(const std::string& host,
                                   unsigned short port,
                                   bool insecure_skip_verify = false,
                                   const std::string& server_name = {});
    void disconnect();
    [[nodiscard]] bool is_connected() const noexcept;

    void set_push_handler(PushHandler handler);

    // Optional: start a background heartbeat. interval_ms=0 to disable.
    void start_heartbeat(unsigned interval_ms);

    // RPCs — each sends a request and blocks until the matching response
    // arrives (or timeout). 2s default timeout; override via set_timeout.
    void set_timeout_ms(unsigned ms) { rpc_timeout_ms_ = ms; }

    [[nodiscard]] LoginResult login(const std::string& username,
                                    const std::string& password,
                                    const std::string& device_id);
    [[nodiscard]] RegisterResult register_user(const std::string& username,
                                               const std::string& password,
                                               const std::string& display_name,
                                               const std::string& device_id);
    [[nodiscard]] ProfileResult profile_get();
    [[nodiscard]] ProfileResult profile_update(const std::string& display_name);
    [[nodiscard]] UserSearchResult search_users(const std::string& query, int limit = 20);
    [[nodiscard]] MessageSearchResult search_messages(const std::string& query,
                                                      const std::string& conversation_id = {},
                                                      int limit = 50,
                                                      int offset = 0);
    [[nodiscard]] SyncResult conversation_sync();
    [[nodiscard]] SyncResult conversation_sync_since(const std::vector<SyncCursor>& cursors);
    [[nodiscard]] SyncResult conversation_history_page(const std::string& conversation_id,
                                                       const std::string& before_message_id = {},
                                                       int limit = 50);
    [[nodiscard]] MessageResult send_message(const std::string& conversation_id,
                                             const std::string& text);
    [[nodiscard]] MessageResult reply_message(const std::string& conversation_id,
                                              const std::string& reply_to_message_id,
                                              const std::string& text);
    [[nodiscard]] MessageResult forward_message(const std::string& source_conversation_id,
                                                const std::string& source_message_id,
                                                const std::string& target_conversation_id);
    [[nodiscard]] MessageReactionResult toggle_reaction(const std::string& conversation_id,
                                                        const std::string& message_id,
                                                        const std::string& emoji);
    [[nodiscard]] MessagePinResult set_message_pin(const std::string& conversation_id,
                                                   const std::string& message_id,
                                                   bool pinned);
    [[nodiscard]] MessageResult send_attachment(const std::string& conversation_id,
                                                const std::string& caption,
                                                const std::string& filename,
                                                const std::string& mime_type,
                                                const std::string& content);

    // M126: chunked upload for files larger than ~1 MB. Calls
    // ATTACHMENT_UPLOAD_INIT/CHUNK/COMPLETE in sequence; the optional
    // `progress` callback is invoked after each successful chunk ack with
    // (bytes_uploaded, bytes_total) so the desktop UI can drive a real
    // byte-level progress bar instead of stage labels.
    using ChunkedUploadProgressCallback =
        std::function<void(std::size_t bytes_uploaded, std::size_t bytes_total)>;
    [[nodiscard]] MessageResult send_attachment_chunked(
        const std::string& conversation_id,
        const std::string& caption,
        const std::string& filename,
        const std::string& mime_type,
        const std::string& content,
        ChunkedUploadProgressCallback progress = {},
        std::size_t chunk_size = 256 * 1024);
    [[nodiscard]] AttachmentFetchResult fetch_attachment(const std::string& attachment_id);
    [[nodiscard]] AckResult mark_read(const std::string& conversation_id,
                                      const std::string& message_id);
    // M147: client-side typing pulse. Returns AckResult so callers can
    // surface server-side rejection (e.g. CONVERSATION_ACCESS_DENIED) but
    // most callers fire-and-forget — typing is an opportunistic UX
    // signal and clients decay locally after ~5s.
    [[nodiscard]] AckResult send_typing_pulse(const std::string& conversation_id,
                                              bool is_typing);
    [[nodiscard]] MessageResult edit_message(const std::string& conversation_id,
                                             const std::string& message_id,
                                             const std::string& new_text);
    [[nodiscard]] AckResult delete_message(const std::string& conversation_id,
                                           const std::string& message_id);
    [[nodiscard]] ContactListResult list_contacts();
    [[nodiscard]] ContactListResult add_contact(const std::string& target_user_id);
    [[nodiscard]] ContactListResult remove_contact(const std::string& target_user_id);
    [[nodiscard]] ConversationActionResult create_conversation(
        const std::vector<std::string>& participant_user_ids,
        const std::string& title);
    [[nodiscard]] ConversationActionResult add_conversation_participant(
        const std::string& conversation_id,
        const std::string& user_id);
    [[nodiscard]] ConversationActionResult remove_conversation_participant(
        const std::string& conversation_id,
        const std::string& user_id);
    [[nodiscard]] DeviceListResult list_devices();
    [[nodiscard]] DeviceListResult revoke_device(const std::string& device_id);
    [[nodiscard]] DeviceListResult update_device_trust(const std::string& device_id, bool trusted);
    [[nodiscard]] PresenceResult presence_query(const std::vector<std::string>& user_ids);
    [[nodiscard]] AckResult heartbeat_ping();

    // Remote-control RPCs (modern client). The legacy session_gateway_client
    // covers the same surface for the scripted app_shell demo.
    [[nodiscard]] RemoteSessionStateResult remote_invite(
        const std::string& requester_device_id,
        const std::string& target_device_id);
    [[nodiscard]] RemoteRelayAssignmentResult remote_approve(
        const std::string& remote_session_id);
    [[nodiscard]] RemoteSessionTerminatedResult remote_reject(
        const std::string& remote_session_id);
    [[nodiscard]] RemoteSessionTerminatedResult remote_cancel(
        const std::string& remote_session_id);
    [[nodiscard]] RemoteSessionTerminatedResult remote_terminate(
        const std::string& remote_session_id);
    [[nodiscard]] RemoteSessionTerminatedResult remote_disconnect(
        const std::string& remote_session_id,
        const std::string& reason = "peer_disconnected");
    [[nodiscard]] RemoteRendezvousResult remote_rendezvous_request(
        const std::string& remote_session_id);

    // M122: voice/video calls
    [[nodiscard]] CallStateResult call_invite(const std::string& callee_user_id,
                                              const std::string& callee_device_id,
                                              const std::string& kind);
    [[nodiscard]] CallStateResult call_accept(const std::string& call_id);
    [[nodiscard]] CallStateResult call_decline(const std::string& call_id);
    [[nodiscard]] CallStateResult call_end(const std::string& call_id);
    // data_json must be a JSON object literal like '{"key":"a"}'
    [[nodiscard]] RemoteInputAckResult remote_input_event(
        const std::string& remote_session_id,
        const std::string& kind,
        const std::string& data_json);

    [[nodiscard]] const std::string& session_id() const noexcept { return session_id_; }
    [[nodiscard]] const std::string& user_id() const noexcept { return user_id_; }

private:
    void dispatcher_loop();
    void heartbeat_loop();

    [[nodiscard]] std::string next_correlation_id();
    [[nodiscard]] int next_sequence();

    [[nodiscard]] std::string compose_envelope(const std::string& type,
                                               const std::string& correlation_id,
                                               const std::string& payload_body);
    [[nodiscard]] std::optional<std::string> send_and_wait(const std::string& type,
                                                           const std::string& payload_body);

    net::TcpLineClient tcp_;
    std::string session_id_;
    std::string user_id_;
    std::atomic<int> correlation_counter_ {0};
    std::atomic<int> sequence_counter_ {0};

    unsigned rpc_timeout_ms_ {3000};

    std::atomic<bool> running_ {false};
    std::thread dispatcher_;
    std::thread heartbeat_;
    std::atomic<unsigned> heartbeat_interval_ms_ {0};

    std::mutex handler_mutex_;
    PushHandler push_handler_;
};

}  // namespace telegram_like::client::transport
