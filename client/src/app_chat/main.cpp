// Interactive C++ chat client built on ControlPlaneClient.
//
// Usage:
//   app_chat --user alice --password alice_pw --device dev_alice_win [--port 8787]
//
// Slash commands at the prompt:
//   /sync                    re-pull conversation history
//   /read <msg_id>           mark message as read
//   /edit <msg_id> <text>    edit a message you sent
//   /del  <msg_id>           soft-delete a message you sent
//   /contacts                list your contacts
//   /add  <user_id>          add a contact
//   /presence <uid>..        query online status
//   /q                       quit
// Anything else = send as message to the current conversation.

#include "transport/control_plane_client.h"

#include <cstring>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Args {
    std::string user;
    std::string password;
    std::string device;
    std::string host = "127.0.0.1";
    unsigned short port = 8787;
    bool tls = false;
    bool tls_insecure = false;
    std::string tls_server_name;
    std::string conversation = "conv_alice_bob";
    unsigned heartbeat_ms = 10000;
};

bool parse_args(int argc, char** argv, Args& out) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&](const std::string& name) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "missing value for " << name << "\n";
                return nullptr;
            }
            return argv[++i];
        };
        if (a == "--user") { const char* v = next(a); if (!v) return false; out.user = v; }
        else if (a == "--password") { const char* v = next(a); if (!v) return false; out.password = v; }
        else if (a == "--device") { const char* v = next(a); if (!v) return false; out.device = v; }
        else if (a == "--host") { const char* v = next(a); if (!v) return false; out.host = v; }
        else if (a == "--port") { const char* v = next(a); if (!v) return false;
            out.port = static_cast<unsigned short>(std::atoi(v)); }
        else if (a == "--tls") { out.tls = true; }
        else if (a == "--tls-insecure") { out.tls = true; out.tls_insecure = true; }
        else if (a == "--tls-server-name") { const char* v = next(a); if (!v) return false; out.tls_server_name = v; }
        else if (a == "--conversation") { const char* v = next(a); if (!v) return false; out.conversation = v; }
        else if (a == "--heartbeat") { const char* v = next(a); if (!v) return false;
            out.heartbeat_ms = static_cast<unsigned>(std::atoi(v)); }
        else {
            std::cerr << "unknown arg: " << a << "\n";
            return false;
        }
    }
    if (out.user.empty() || out.password.empty() || out.device.empty()) {
        std::cerr << "--user / --password / --device are required\n";
        return false;
    }
    return true;
}

std::vector<std::string> split_whitespace(const std::string& s, std::size_t max_parts = 0) {
    std::vector<std::string> parts;
    std::size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\t')) ++i;
        if (i >= s.size()) break;
        if (max_parts > 0 && parts.size() + 1 == max_parts) {
            parts.emplace_back(s.substr(i));
            break;
        }
        std::size_t start = i;
        while (i < s.size() && s[i] != ' ' && s[i] != '\t') ++i;
        parts.emplace_back(s.substr(start, i - start));
    }
    return parts;
}

std::string json_find_string(const std::string& line, const std::string& key) {
    // Ultra-lightweight: find `"key"` then skip `:` and optional whitespace
    // before reading the quoted value. Handles Python json.dumps default
    // separator (", ") and compact separators alike.
    const std::string key_marker = "\"" + key + "\"";
    auto pos = line.find(key_marker);
    if (pos == std::string::npos) return {};
    pos += key_marker.size();
    while (pos < line.size() && (line[pos] == ' ' || line[pos] == '\t')) ++pos;
    if (pos >= line.size() || line[pos] != ':') return {};
    ++pos;
    while (pos < line.size() && (line[pos] == ' ' || line[pos] == '\t')) ++pos;
    if (pos >= line.size() || line[pos] != '"') return {};
    ++pos;
    std::string out;
    while (pos < line.size()) {
        char c = line[pos];
        if (c == '\\' && pos + 1 < line.size()) {
            char next = line[pos + 1];
            if (next == 'n') out += '\n';
            else if (next == 't') out += '\t';
            else out += next;
            pos += 2;
            continue;
        }
        if (c == '"') break;
        out += c;
        ++pos;
    }
    return out;
}

void print_push(const std::string& type, const std::string& envelope,
                const std::string& current_user, const std::string& prompt,
                std::mutex& stdout_mutex) {
    std::lock_guard lock(stdout_mutex);
    std::cout << "\r";
    if (type == "message_deliver") {
        const std::string sender = json_find_string(envelope, "sender_user_id");
        const std::string text = json_find_string(envelope, "text");
        const std::string attach = json_find_string(envelope, "attachment_id");
        const std::string mid = json_find_string(envelope, "message_id");
        std::cout << "[" << sender << "] " << text;
        if (!attach.empty()) std::cout << " [attach=" << attach << "]";
        std::cout << "  (msg=" << mid << ")\n";
    } else if (type == "message_edited") {
        std::cout << "[edit by " << json_find_string(envelope, "sender_user_id")
                  << "] msg=" << json_find_string(envelope, "message_id")
                  << " -> " << json_find_string(envelope, "text") << "\n";
    } else if (type == "message_deleted") {
        std::cout << "[delete by " << json_find_string(envelope, "sender_user_id")
                  << "] msg=" << json_find_string(envelope, "message_id") << "\n";
    } else if (type == "message_read_update") {
        std::cout << "[read] " << json_find_string(envelope, "reader_user_id")
                  << " up to " << json_find_string(envelope, "last_read_message_id") << "\n";
    } else if (type == "conversation_updated") {
        std::cout << "[conversation_updated] conv="
                  << json_find_string(envelope, "conversation_id") << "\n";
    } else {
        std::cout << "[push " << type << "] " << envelope << "\n";
    }
    std::cout << prompt << std::flush;
    (void)current_user;
}

}  // namespace

int main(int argc, char** argv) {
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: app_chat --user X --password X --device X [--host 127.0.0.1] "
                     "[--port 8787] [--tls] [--tls-insecure] [--tls-server-name localhost] "
                     "[--conversation conv_alice_bob] [--heartbeat 10000]\n";
        return 2;
    }

    telegram_like::client::transport::ControlPlaneClient client;
    const bool connected = args.tls
        ? client.connect_tls(args.host, args.port, args.tls_insecure, args.tls_server_name)
        : client.connect(args.host, args.port);
    if (!connected) {
        std::cerr << "could not connect to " << args.host << ":" << args.port << "\n";
        return 1;
    }

    const auto login = client.login(args.user, args.password, args.device);
    if (!login.ok) {
        std::cerr << "login failed: " << login.error_code << " " << login.error_message << "\n";
        return 1;
    }
    std::cout << "logged in as " << login.user_id
              << " (session " << login.session_id << ")\n"
              << "chatting in " << args.conversation << ". type '/q' to quit.\n";

    const std::string prompt = login.user_id + "> ";
    std::mutex stdout_mutex;

    client.set_push_handler([&](const std::string& type, const std::string& envelope) {
        print_push(type, envelope, login.user_id, prompt, stdout_mutex);
    });

    if (args.heartbeat_ms > 0) {
        client.start_heartbeat(args.heartbeat_ms);
    }

    // Initial sync so the user sees existing history.
    {
        const auto sync = client.conversation_sync();
        std::lock_guard lock(stdout_mutex);
        std::cout << "[sync]\n";
        for (const auto& c : sync.conversations) {
            std::cout << "  " << c.conversation_id;
            if (!c.title.empty()) std::cout << " '" << c.title << "'";
            std::cout << " participants=[";
            for (std::size_t i = 0; i < c.participant_user_ids.size(); ++i) {
                if (i) std::cout << ",";
                std::cout << c.participant_user_ids[i];
            }
            std::cout << "]\n";
            const std::size_t tail = c.messages.size() > 10 ? c.messages.size() - 10 : 0;
            for (std::size_t i = tail; i < c.messages.size(); ++i) {
                const auto& m = c.messages[i];
                std::cout << "    " << m.message_id
                          << " [" << m.sender_user_id << "] "
                          << (m.deleted ? std::string("<deleted>") : m.text);
                if (m.edited) std::cout << " (edited)";
                if (!m.attachment_id.empty()) std::cout << " [attach=" << m.attachment_id << "]";
                std::cout << "\n";
            }
        }
    }

    std::string line;
    while (true) {
        {
            std::lock_guard lock(stdout_mutex);
            std::cout << prompt << std::flush;
        }
        if (!std::getline(std::cin, line)) break;

        if (line.empty()) continue;
        if (line == "/q") break;

        auto emit_error = [&](const std::string& code, const std::string& msg) {
            std::lock_guard lock(stdout_mutex);
            std::cout << "[ERR " << code << "] " << msg << "\n";
        };

        if (line == "/sync") {
            const auto sync = client.conversation_sync();
            if (!sync.ok) { emit_error(sync.error_code, sync.error_message); continue; }
            std::lock_guard lock(stdout_mutex);
            std::cout << "[sync]\n";
            for (const auto& c : sync.conversations) {
                std::cout << "  " << c.conversation_id;
                if (!c.title.empty()) std::cout << " '" << c.title << "'";
                std::cout << " participants=[";
                for (std::size_t i = 0; i < c.participant_user_ids.size(); ++i) {
                    if (i) std::cout << ",";
                    std::cout << c.participant_user_ids[i];
                }
                std::cout << "]\n";
                const std::size_t tail = c.messages.size() > 10 ? c.messages.size() - 10 : 0;
                for (std::size_t i = tail; i < c.messages.size(); ++i) {
                    const auto& m = c.messages[i];
                    std::cout << "    " << m.message_id
                              << " [" << m.sender_user_id << "] "
                              << (m.deleted ? std::string("<deleted>") : m.text);
                    if (m.edited) std::cout << " (edited)";
                    std::cout << "\n";
                }
            }
            continue;
        }

        if (line == "/contacts") {
            const auto r = client.list_contacts();
            if (!r.ok) { emit_error(r.error_code, r.error_message); continue; }
            std::lock_guard lock(stdout_mutex);
            std::cout << "[contacts]\n";
            if (r.contacts.empty()) { std::cout << "  (empty)\n"; }
            for (const auto& c : r.contacts) {
                std::cout << "  " << c.user_id << " (" << c.display_name << ") "
                          << (c.online ? "online" : "offline") << "\n";
            }
            continue;
        }

        if (line.rfind("/add ", 0) == 0) {
            const std::string target = line.substr(5);
            const auto r = client.add_contact(target);
            if (!r.ok) { emit_error(r.error_code, r.error_message); continue; }
            std::lock_guard lock(stdout_mutex);
            std::cout << "[contact added] you now have " << r.contacts.size() << " contact(s)\n";
            continue;
        }

        if (line.rfind("/presence ", 0) == 0) {
            auto parts = split_whitespace(line.substr(10));
            const auto r = client.presence_query(parts);
            if (!r.ok) { emit_error(r.error_code, r.error_message); continue; }
            std::lock_guard lock(stdout_mutex);
            std::cout << "[presence]\n";
            for (const auto& u : r.users) {
                std::cout << "  " << u.user_id << ": " << (u.online ? "online" : "offline")
                          << " (last_seen_at_ms=" << u.last_seen_at_ms << ")\n";
            }
            continue;
        }

        if (line.rfind("/read ", 0) == 0) {
            const std::string mid = line.substr(6);
            const auto r = client.mark_read(args.conversation, mid);
            if (!r.ok) emit_error(r.error_code, r.error_message);
            continue;
        }

        if (line.rfind("/edit ", 0) == 0) {
            auto parts = split_whitespace(line.substr(6), 2);
            if (parts.size() != 2) { emit_error("usage", "/edit <msg_id> <text>"); continue; }
            const auto r = client.edit_message(args.conversation, parts[0], parts[1]);
            if (!r.ok) emit_error(r.error_code, r.error_message);
            continue;
        }

        if (line.rfind("/del ", 0) == 0) {
            const std::string mid = line.substr(5);
            const auto r = client.delete_message(args.conversation, mid);
            if (!r.ok) emit_error(r.error_code, r.error_message);
            continue;
        }

        if (!line.empty() && line[0] == '/') {
            emit_error("unknown_command", line);
            continue;
        }

        const auto r = client.send_message(args.conversation, line);
        if (!r.ok) emit_error(r.error_code, r.error_message);
    }

    client.disconnect();
    return 0;
}
