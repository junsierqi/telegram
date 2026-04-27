#include "app_desktop/desktop_chat_store.h"

#include <iostream>
#include <cstdio>
#include <string>

using telegram_like::client::app_desktop::DesktopChatStore;
using telegram_like::client::transport::MessageResult;
using telegram_like::client::transport::ReadMarker;
using telegram_like::client::transport::SyncResult;
using telegram_like::client::transport::SyncedConversation;
using telegram_like::client::transport::SyncedMessage;

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "[FAIL] " << message << "\n";
        std::exit(1);
    }
}

std::string deliver_push(const std::string& conversation_id,
                         const std::string& message_id,
                         const std::string& sender,
                         const std::string& text) {
    return "{\"type\":\"message_deliver\",\"correlation_id\":\"push_1\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\","
           "\"sender_user_id\":\"" + sender + "\","
           "\"text\":\"" + text + "\"}}";
}

std::string read_push(const std::string& conversation_id,
                      const std::string& reader,
                      const std::string& message_id) {
    return "{\"type\":\"message_read_update\",\"correlation_id\":\"push_read\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"reader_user_id\":\"" + reader + "\","
           "\"last_read_message_id\":\"" + message_id + "\"}}";
}

std::string attachment_deliver_push(const std::string& conversation_id,
                                    const std::string& message_id,
                                    const std::string& sender,
                                    const std::string& text,
                                    const std::string& attachment_id,
                                    const std::string& filename,
                                    const std::string& mime_type,
                                    int size_bytes) {
    return "{\"type\":\"message_deliver\",\"correlation_id\":\"push_attachment\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\","
           "\"sender_user_id\":\"" + sender + "\","
           "\"text\":\"" + text + "\","
           "\"attachment_id\":\"" + attachment_id + "\","
           "\"filename\":\"" + filename + "\","
           "\"mime_type\":\"" + mime_type + "\","
           "\"size_bytes\":" + std::to_string(size_bytes) + "}}";
}

std::string edit_push(const std::string& conversation_id,
                      const std::string& message_id,
                      const std::string& text) {
    return "{\"type\":\"message_edited\",\"correlation_id\":\"push_edit\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\","
           "\"text\":\"" + text + "\"}}";
}

std::string delete_push(const std::string& conversation_id,
                        const std::string& message_id) {
    return "{\"type\":\"message_deleted\",\"correlation_id\":\"push_del\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\"}}";
}

std::string reaction_push(const std::string& conversation_id,
                          const std::string& message_id,
                          const std::string& summary) {
    return "{\"type\":\"message_reaction_updated\",\"correlation_id\":\"push_react\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\","
           "\"reaction_summary\":\"" + summary + "\"}}";
}

std::string pin_push(const std::string& conversation_id,
                     const std::string& message_id,
                     bool pinned) {
    return "{\"type\":\"message_pin_updated\",\"correlation_id\":\"push_pin\",\"payload\":{"
           "\"conversation_id\":\"" + conversation_id + "\","
           "\"message_id\":\"" + message_id + "\","
           "\"pinned\":" + std::string(pinned ? "true" : "false") + "}}";
}

SyncResult seed_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob";
    conv.participant_user_ids = {"u_alice", "u_bob"};
    conv.version = 2;
    SyncedMessage msg;
    msg.message_id = "msg_1";
    msg.sender_user_id = "u_bob";
    msg.text = "seed";
    conv.messages.push_back(msg);
    sync.conversations.push_back(conv);
    return sync;
}

SyncResult reconciled_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob";
    conv.participant_user_ids = {"u_alice", "u_bob"};
    conv.version = 3;
    SyncedMessage msg;
    msg.message_id = "msg_1";
    msg.sender_user_id = "u_bob";
    msg.text = "server truth after reconnect";
    msg.edited = true;
    conv.messages.push_back(msg);
    sync.conversations.push_back(conv);
    return sync;
}

SyncResult incremental_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob";
    conv.participant_user_ids = {"u_alice", "u_bob"};
    conv.version = 4;
    SyncedMessage msg;
    msg.message_id = "msg_5";
    msg.sender_user_id = "u_bob";
    msg.text = "incremental";
    conv.messages.push_back(msg);
    sync.conversations.push_back(conv);
    return sync;
}

SyncResult history_page_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob";
    conv.participant_user_ids = {"u_alice", "u_bob"};
    conv.next_before_message_id = "msg_0";
    conv.has_more = true;
    SyncedMessage older;
    older.message_id = "msg_0";
    older.sender_user_id = "u_alice";
    older.text = "older page";
    conv.messages.push_back(older);
    sync.conversations.push_back(conv);
    return sync;
}

SyncResult incremental_change_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob";
    conv.participant_user_ids = {"u_alice", "u_bob"};
    conv.version = 5;
    telegram_like::client::transport::SyncedChange change;
    change.version = 5;
    change.kind = "message_edited";
    change.message_id = "msg_5";
    change.sender_user_id = "u_bob";
    change.text = "incremental edited";
    conv.changes.push_back(change);
    sync.conversations.push_back(conv);
    return sync;
}

SyncResult incremental_metadata_sync() {
    SyncResult sync;
    sync.ok = true;
    SyncedConversation conv;
    conv.conversation_id = "conv_alice_bob";
    conv.title = "Alice / Bob / Carol";
    conv.participant_user_ids = {"u_alice", "u_bob", "u_carol"};
    conv.version = 9;
    telegram_like::client::transport::SyncedChange change;
    change.version = 9;
    change.kind = "conversation_updated";
    conv.changes.push_back(change);
    sync.conversations.push_back(conv);
    return sync;
}

}  // namespace

int main() {
    DesktopChatStore store;
    store.set_current_user("u_alice");
    store.set_selected_conversation("conv_alice_bob");
    store.apply_sync(seed_sync());

    require(store.selected_conversation() != nullptr, "selected conversation missing after sync");
    require(store.selected_conversation()->messages.size() == 1, "seed message missing");
    require(store.last_message_id("conv_alice_bob") == "msg_1", "initial cursor missing");
    require(store.render_selected_transcript().find("<< [legacy] u_bob | received | msg_1") != std::string::npos,
            "rendered transcript missing inbound bubble header");
    require(store.render_selected_transcript().find("   seed") != std::string::npos,
            "rendered transcript missing seed message body");
    require(store.render_selected_timeline_html().find("class='row in") != std::string::npos,
            "rich timeline html missing inbound row");
    require(!store.filtered_conversations("bob").empty(),
            "conversation filter should match participant/title/message text");
    require(store.filtered_conversations("not-present").empty(),
            "conversation filter should hide non-matching conversations");
    const auto seed_search = store.search_selected_messages("seed");
    require(seed_search.size() == 1 && seed_search.front().message_id == "msg_1",
            "selected message search did not find seed message");
    const auto highlighted_seed = store.render_selected_timeline_html("seed", "msg_1");
    require(highlighted_seed.find("match") != std::string::npos
                && highlighted_seed.find("focused") != std::string::npos,
            "rich timeline html missing search match/focused markers");

    const auto local_id = store.add_pending_message("conv_alice_bob", "pending text", 1710000005000);
    require(local_id.rfind("local_", 0) == 0, "pending message id should be local");
    require(store.render_selected_transcript().find("pending | " + local_id) != std::string::npos,
            "pending message state not rendered");
    require(store.last_message_id("conv_alice_bob") == "msg_1",
            "pending local message should not advance server cursor");

    MessageResult sent;
    sent.ok = true;
    sent.message_id = "msg_2";
    sent.sender_user_id = "u_alice";
    sent.text = "local send";
    sent.created_at_ms = 1710000000000;
    sent.attachment_id = "att_local";
    sent.filename = "local.txt";
    sent.mime_type = "text/plain";
    sent.size_bytes = 12;
    sent.preview_text = "hello local";
    sent.reply_to_message_id = "msg_1";
    store.resolve_pending_message("conv_alice_bob", local_id, sent);
    require(store.selected_conversation()->messages.size() == 2, "sent message not merged");
    require(store.last_message_id("conv_alice_bob") == "msg_2", "cursor did not advance after local send");
    require(store.latest_attachment_id("conv_alice_bob") == "att_local",
            "sent attachment id was not stored");
    require(store.latest_attachment_filename("conv_alice_bob") == "local.txt",
            "sent attachment filename was not stored");
    require(store.attachment_filename("conv_alice_bob", "att_local") == "local.txt",
            "attachment filename lookup by id failed");
    require(store.render_selected_transcript().find("file=local.txt mime=text/plain bytes=12") != std::string::npos,
            "rendered transcript missing attachment metadata");
    require(store.render_selected_transcript().find("preview=\"hello local\"") != std::string::npos,
            "rendered transcript missing text attachment preview");
    require(store.render_selected_transcript().find("[reply_to=msg_1]") != std::string::npos,
            "rendered transcript missing reply metadata");
    require(store.render_selected_transcript().find(">> [") != std::string::npos
                && store.render_selected_transcript().find("u_alice | sent | msg_2") != std::string::npos,
            "rendered transcript missing outbound sent bubble state");
    require(store.render_selected_timeline_html().find("class='row out") != std::string::npos
                && store.render_selected_timeline_html().find("d7f3c9") != std::string::npos,
            "rich timeline html missing outbound bubble styling");
    require(store.render_selected_timeline_html().find("href='msg://msg_2'") != std::string::npos,
            "rich timeline html missing clickable message action target link");

    store.apply_push("message_read_update", read_push("conv_alice_bob", "u_bob", "msg_2"));
    require(store.render_selected_transcript().find("u_alice | read | msg_2") != std::string::npos,
            "read marker did not promote outbound message to read");

    const auto failed_id = store.add_pending_message("conv_alice_bob", "will fail", 1710000006000);
    store.fail_pending_message("conv_alice_bob", failed_id, "transport_error");
    require(store.render_selected_transcript().find("failed: transport_error | " + failed_id) != std::string::npos,
            "failed pending message state not rendered");
    require(store.render_selected_timeline_html().find("failed") != std::string::npos,
            "rich timeline html missing failed marker");

    const auto pending_attachment_id = store.add_pending_attachment_message(
        "conv_alice_bob", "pending upload", "upload.bin", "application/octet-stream", 7, 1710000007000
    );
    require(store.render_selected_transcript().find("pending | " + pending_attachment_id) != std::string::npos
                && store.render_selected_transcript().find("file=upload.bin") != std::string::npos,
            "pending attachment message state not rendered");

    store.apply_push("message_deliver",
                     attachment_deliver_push("conv_alice_bob", "msg_img", "u_bob", "image",
                                             "att_img", "cat.png", "image/png", 42));
    require(store.render_selected_transcript().find("preview=image") != std::string::npos,
            "rendered transcript missing image attachment preview affordance");

    store.apply_push("message_deliver",
                     deliver_push("conv_alice_bob", "msg_3", "u_bob", "remote push"));
    require(store.selected_conversation()->messages.size() == 6, "push message not merged");
    require(store.last_message_id("conv_alice_bob") == "msg_3", "cursor did not advance after push");
    require(store.selected_conversation()->unread_count == 0, "selected push should not count unread");

    store.apply_push("message_edited", edit_push("conv_alice_bob", "msg_3", "remote edited"));
    require(store.render_selected_transcript().find("remote edited (edited)") != std::string::npos,
            "edit push not reflected");

    store.apply_push("message_reaction_updated", reaction_push("conv_alice_bob", "msg_3", "+1:1"));
    require(store.render_selected_transcript().find("[reactions=+1:1]") != std::string::npos,
            "reaction push not reflected");
    store.apply_push("message_pin_updated", pin_push("conv_alice_bob", "msg_3", true));
    require(store.render_selected_transcript().find("[pinned]") != std::string::npos,
            "pin push not reflected");

    store.apply_push("message_deleted", delete_push("conv_alice_bob", "msg_3"));
    require(store.render_selected_transcript().find("u_bob | received | msg_3") != std::string::npos
                && store.render_selected_transcript().find("   <deleted>") != std::string::npos,
            "delete push not reflected");

    store.apply_push("message_deliver", deliver_push("conv_group", "msg_4", "u_bob", "other conv"));
    auto conversations = store.conversations();
    bool found_unread = false;
    for (const auto& conv : conversations) {
        if (conv.conversation_id == "conv_group" && conv.unread_count == 1) {
            found_unread = true;
        }
    }
    require(found_unread, "unselected conversation unread count not incremented");

    const std::string cache_path = ".tmp_app_desktop_store_test_cache.json";
    std::remove(cache_path.c_str());
    std::string error;
    require(store.save_to_file(cache_path, &error), "store save_to_file failed");

    DesktopChatStore loaded;
    require(loaded.load_from_file(cache_path, &error), "store load_from_file failed");
    loaded.set_selected_conversation("conv_alice_bob");
    require(loaded.render_selected_transcript().find("u_alice | read | msg_2") != std::string::npos
                && loaded.render_selected_transcript().find("   local send") != std::string::npos,
            "loaded cache missing sent message");
    require(loaded.render_selected_transcript().find("failed: transport_error") != std::string::npos,
            "loaded cache missing failed local message");
    require(loaded.latest_attachment_id("conv_alice_bob") == "att_img",
            "loaded cache missing latest attachment id");
    require(loaded.latest_attachment_filename("conv_alice_bob") == "cat.png",
            "loaded cache missing latest attachment filename");
    require(loaded.attachment_filename("conv_alice_bob", "att_local") == "local.txt",
            "attachment filename lookup by id failed after cache load");
    require(loaded.render_selected_transcript().find("preview=\"hello local\"") != std::string::npos,
            "loaded cache missing text attachment preview");
    require(loaded.render_selected_transcript().find("[reply_to=msg_1]") != std::string::npos,
            "loaded cache missing reply metadata");
    require(loaded.render_selected_transcript().find("[pinned]") != std::string::npos,
            "loaded cache missing pin state");
    require(loaded.render_selected_transcript().find("[reactions=+1:1]") != std::string::npos,
            "loaded cache missing reaction summary");
    require(loaded.render_selected_transcript().find("preview=image") != std::string::npos,
            "loaded cache missing image attachment preview affordance");
    require(loaded.last_message_id("conv_alice_bob") == "msg_3",
            "loaded cache missing last_message_id cursor");
    const auto cursors = loaded.sync_cursors();
    require(!cursors.empty() && cursors.front().conversation_id == "conv_alice_bob"
                && cursors.front().last_message_id == "msg_3",
            "sync_cursors missing persisted last_message_id");

    loaded.apply_incremental_sync(incremental_sync());
    require(loaded.render_selected_transcript().find("u_bob | received | msg_5") != std::string::npos
                && loaded.render_selected_transcript().find("   incremental") != std::string::npos,
            "incremental sync did not merge new message");
    require(loaded.render_selected_transcript().find("u_alice | read | msg_2") != std::string::npos
                && loaded.render_selected_transcript().find("   local send") != std::string::npos,
            "incremental sync should preserve cached prior messages");
    require(loaded.last_message_id("conv_alice_bob") == "msg_5",
            "incremental sync did not advance cursor");
    require(loaded.sync_cursors().front().version == 4,
            "incremental sync did not persist server version");

    loaded.apply_incremental_sync(incremental_change_sync());
    require(loaded.render_selected_transcript().find("incremental edited (edited)") != std::string::npos,
            "incremental change sync did not apply edit delta");
    require(loaded.sync_cursors().front().version == 5,
            "incremental change sync did not advance version");

    SyncResult action_delta_sync;
    action_delta_sync.ok = true;
    SyncedConversation action_conv;
    action_conv.conversation_id = "conv_alice_bob";
    action_conv.title = "Alice / Bob";
    action_conv.participant_user_ids = {"u_alice", "u_bob"};
    action_conv.version = 7;
    telegram_like::client::transport::SyncedChange reaction_change;
    reaction_change.version = 7;
    reaction_change.kind = "message_reaction_updated";
    reaction_change.message_id = "msg_5";
    reaction_change.reaction_summary = "+1:2";
    action_conv.changes.push_back(reaction_change);
    telegram_like::client::transport::SyncedChange pin_change;
    pin_change.version = 8;
    pin_change.kind = "message_pin_updated";
    pin_change.message_id = "msg_5";
    pin_change.pinned = true;
    action_conv.changes.push_back(pin_change);
    action_delta_sync.conversations.push_back(action_conv);
    loaded.apply_incremental_sync(action_delta_sync);
    require(loaded.render_selected_transcript().find("[reactions=+1:2]") != std::string::npos
                && loaded.render_selected_transcript().find("[pinned]") != std::string::npos,
            "incremental message action deltas not rendered");

    loaded.apply_incremental_sync(incremental_metadata_sync());
    const auto after_metadata = loaded.conversations();
    require(!after_metadata.empty() && after_metadata.front().title == "Alice / Bob / Carol",
            "incremental metadata sync did not update title");
    require(after_metadata.front().participant_user_ids.size() == 3,
            "incremental metadata sync did not update participants");
    require(loaded.sync_cursors().front().version == 9,
            "incremental metadata sync did not advance version");

    SyncResult group_sync;
    group_sync.ok = true;
    SyncedConversation group;
    group.conversation_id = "conv_team";
    group.title = "Team";
    group.participant_user_ids = {"u_alice", "u_bob", "u_carol"};
    SyncedMessage group_msg;
    group_msg.message_id = "msg_10";
    group_msg.sender_user_id = "u_alice";
    group_msg.text = "team update";
    group.messages.push_back(group_msg);
    group.read_markers.push_back(ReadMarker {.user_id = "u_bob", .last_read_message_id = "msg_10"});
    group_sync.conversations.push_back(group);
    loaded.apply_sync(group_sync);
    loaded.set_current_user("u_alice");
    loaded.set_selected_conversation("conv_team");
    require(loaded.render_selected_transcript().find("read by u_bob | msg_10") != std::string::npos,
            "group partial read details missing");
    loaded.apply_push("message_read_update", read_push("conv_team", "u_carol", "msg_10"));
    require(loaded.render_selected_transcript().find("read by all | msg_10") != std::string::npos,
            "group all-read details missing");

    loaded.apply_sync(reconciled_sync());
    loaded.set_selected_conversation("conv_alice_bob");
    require(loaded.render_selected_transcript().find("server truth after reconnect (edited)") != std::string::npos,
            "sync reconciliation did not apply server truth");
    require(loaded.render_selected_transcript().find("local send") == std::string::npos,
            "sync reconciliation left stale local-only message");
    loaded.apply_history_page(history_page_sync());
    require(loaded.render_selected_transcript().find("older page") != std::string::npos,
            "history page did not prepend older message");
    require(loaded.history_has_more("conv_alice_bob"),
            "history page did not retain has_more");
    require(loaded.history_next_before_message_id("conv_alice_bob") == "msg_0",
            "history page did not retain next_before_message_id");
    std::remove(cache_path.c_str());

    std::cout << "[ok ] sync initializes store\n";
    std::cout << "[ok ] sent and pushed messages merge into selected transcript\n";
    std::cout << "[ok ] attachment metadata is retained for local send and cache load\n";
    std::cout << "[ok ] edit/delete pushes mutate existing messages\n";
    std::cout << "[ok ] unread count increments for unselected conversation\n";
    std::cout << "[ok ] cache save/load round-trips store snapshot\n";
    std::cout << "[ok ] reconnect sync reconciles cached state to server truth\n";
    std::cout << "[ok ] per-conversation last_message_id cursor advances and persists\n";
    std::cout << "[ok ] incremental sync merges new messages and advances cursor\n";
    std::cout << "[ok ] incremental change sync applies edits and advances version\n";
    std::cout << "[ok ] incremental metadata sync updates title and participants\n";
    std::cout << "[ok ] timeline renders timestamps, direction bubbles and read state\n";
    std::cout << "[ok ] pending and failed local send states render and persist\n";
    std::cout << "[ok ] group read receipts render per-member details\n";
    std::cout << "[ok ] rich HTML timeline renderer exposes bubble styling\n";
    std::cout << "[ok ] legacy messages render with explicit timestamp fallback\n";
    std::cout << "[ok ] navigation search filters chats and highlights message matches\n";
    std::cout << "[ok ] message actions render replies, reactions and pins\n";
    std::cout << "[ok ] rich timeline exposes clickable message action targets\n";
    std::cout << "[ok ] older history pages merge into the local cache\n";
    std::cout << "passed 20/20\n";
    return 0;
}
