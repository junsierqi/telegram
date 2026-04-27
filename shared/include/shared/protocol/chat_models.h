#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace telegram_like::shared::protocol {

struct UserSummary {
    std::string user_id;
    std::string display_name;
    bool online {false};
};

struct DeviceSummary {
    std::string device_id;
    std::string label;
    std::string platform;
    bool trusted {false};
    bool active {false};
};

struct MessageRecord {
    std::string message_id;
    std::string conversation_id;
    std::string sender_user_id;
    std::string text;
    std::uint64_t created_at_unix_ms {0};
    std::string reply_to_message_id;
    std::string forwarded_from_conversation_id;
    std::string forwarded_from_message_id;
    std::string forwarded_from_sender_user_id;
    std::string reaction_summary;
    bool pinned {false};
};

struct ConversationSnapshot {
    std::string conversation_id;
    std::vector<UserSummary> participants;
    std::vector<MessageRecord> messages;
};

}  // namespace telegram_like::shared::protocol
