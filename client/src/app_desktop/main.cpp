#include "app_desktop/desktop_chat_store.h"
#include "transport/control_plane_client.h"

#include <QApplication>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMainWindow>
#include <QMetaObject>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QSpinBox>
#include <QStatusBar>
#include <QString>
#include <QTextBrowser>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>

#include <atomic>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

using telegram_like::client::transport::ControlPlaneClient;

struct Args {
    std::string user = "alice";
    std::string password = "alice_pw";
    std::string display_name;
    std::string device = "dev_alice_qt";
    std::string host = "127.0.0.1";
    unsigned short port = 8787;
    std::string conversation = "conv_alice_bob";
    std::string cache_file = ".tmp_app_desktop_cache.json";
    std::string smoke_save_dir;
    bool smoke = false;
    bool smoke_attachment = false;
    bool smoke_register = false;
};

bool parse_args(int argc, char** argv, Args& out) {
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto next = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "missing value for " << name << "\n";
                return nullptr;
            }
            return argv[++i];
        };
        if (arg == "--smoke") {
            out.smoke = true;
        } else if (arg == "--smoke-attachment") {
            out.smoke = true;
            out.smoke_attachment = true;
        } else if (arg == "--user") {
            const char* v = next("--user");
            if (!v) return false;
            out.user = v;
        } else if (arg == "--password") {
            const char* v = next("--password");
            if (!v) return false;
            out.password = v;
        } else if (arg == "--display-name") {
            const char* v = next("--display-name");
            if (!v) return false;
            out.display_name = v;
        } else if (arg == "--device") {
            const char* v = next("--device");
            if (!v) return false;
            out.device = v;
        } else if (arg == "--host") {
            const char* v = next("--host");
            if (!v) return false;
            out.host = v;
        } else if (arg == "--port") {
            const char* v = next("--port");
            if (!v) return false;
            out.port = static_cast<unsigned short>(std::atoi(v));
        } else if (arg == "--conversation") {
            const char* v = next("--conversation");
            if (!v) return false;
            out.conversation = v;
        } else if (arg == "--cache-file") {
            const char* v = next("--cache-file");
            if (!v) return false;
            out.cache_file = v;
        } else if (arg == "--smoke-save-dir") {
            const char* v = next("--smoke-save-dir");
            if (!v) return false;
            out.smoke_save_dir = v;
        } else if (arg == "--smoke-register") {
            out.smoke = true;
            out.smoke_register = true;
        } else {
            std::cerr << "unknown arg: " << arg << "\n";
            return false;
        }
    }
    return true;
}

QString qstr(const std::string& value) {
    return QString::fromStdString(value);
}

std::string str(const QString& value) {
    return value.toStdString();
}

std::string guess_mime_type(const QFileInfo& info) {
    const auto suffix = info.suffix().toLower();
    if (suffix == "txt" || suffix == "md" || suffix == "log" || suffix == "csv") return "text/plain";
    if (suffix == "png") return "image/png";
    if (suffix == "jpg" || suffix == "jpeg") return "image/jpeg";
    if (suffix == "gif") return "image/gif";
    if (suffix == "webp") return "image/webp";
    return "application/octet-stream";
}

int run_smoke(const Args& args) {
    ControlPlaneClient client;
    if (!client.connect(args.host, args.port)) {
        std::cerr << "desktop smoke: connect failed\n";
        return 1;
    }
    if (args.smoke_register) {
        const auto reg = client.register_user(
            args.user, args.password, args.display_name.empty() ? args.user : args.display_name, args.device
        );
        if (!reg.ok) {
            std::cerr << "desktop register smoke: register failed " << reg.error_code << " "
                      << reg.error_message << "\n";
            return 1;
        }
        std::cout << "desktop register smoke ok: user=" << reg.user_id
                  << " device=" << reg.device_id << "\n";
        client.disconnect();
        return 0;
    }
    const auto login = client.login(args.user, args.password, args.device);
    if (!login.ok) {
        std::cerr << "desktop smoke: login failed " << login.error_code << " "
                  << login.error_message << "\n";
        return 1;
    }
    const auto sync = client.conversation_sync();
    if (!sync.ok) {
        std::cerr << "desktop smoke: sync failed " << sync.error_code << " "
                  << sync.error_message << "\n";
        return 1;
    }
    telegram_like::client::app_desktop::DesktopChatStore smoke_store;
    smoke_store.set_current_user(login.user_id);
    smoke_store.set_selected_conversation(args.conversation);
    smoke_store.apply_sync(sync);
    const auto filtered_chats = smoke_store.filtered_conversations("alice");
    const auto message_matches = smoke_store.search_selected_messages("hello");
    const auto highlighted = smoke_store.render_selected_timeline_html("hello",
        message_matches.empty() ? std::string {} : message_matches.front().message_id);
    if (filtered_chats.empty() || message_matches.empty()
        || highlighted.find("match") == std::string::npos
        || highlighted.find("focused") == std::string::npos) {
        std::cerr << "desktop smoke: navigation search failed\n";
        return 1;
    }
    std::cout << "desktop navigation search smoke ok: chats=" << filtered_chats.size()
              << " matches=" << message_matches.size()
              << " first=" << message_matches.front().message_id << "\n";
    std::vector<telegram_like::client::transport::SyncCursor> cursors;
    for (const auto& conversation : sync.conversations) {
        if (conversation.conversation_id == args.conversation && !conversation.messages.empty()) {
            cursors.push_back(telegram_like::client::transport::SyncCursor {
                .conversation_id = conversation.conversation_id,
                .last_message_id = conversation.messages.back().message_id,
                .version = conversation.version,
            });
        }
    }
    const auto sent = client.send_message(args.conversation, "hello from Qt desktop smoke");
    if (!sent.ok) {
        std::cerr << "desktop smoke: send failed " << sent.error_code << " "
                  << sent.error_message << "\n";
        return 1;
    }
    std::cout << "desktop smoke ok: user=" << login.user_id
              << " conversations=" << sync.conversations.size()
              << " message_id=" << sent.message_id << "\n";
    smoke_store.apply_sent_message(args.conversation, sent);
    const auto reply = client.reply_message(args.conversation, sent.message_id, "reply from Qt desktop smoke");
    if (!reply.ok || reply.reply_to_message_id != sent.message_id) {
        std::cerr << "desktop smoke: reply failed " << reply.error_code << " "
                  << reply.error_message << "\n";
        return 1;
    }
    smoke_store.apply_sent_message(args.conversation, reply);
    const auto reaction = client.toggle_reaction(args.conversation, sent.message_id, "+1");
    if (!reaction.ok || reaction.reaction_summary.find("+1:1") == std::string::npos) {
        std::cerr << "desktop smoke: reaction failed " << reaction.error_code << " "
                  << reaction.error_message << "\n";
        return 1;
    }
    smoke_store.apply_reaction_summary(args.conversation, sent.message_id, reaction.reaction_summary);
    const auto pinned = client.set_message_pin(args.conversation, sent.message_id, true);
    if (!pinned.ok || !pinned.pinned) {
        std::cerr << "desktop smoke: pin failed " << pinned.error_code << " "
                  << pinned.error_message << "\n";
        return 1;
    }
    smoke_store.apply_pin_state(args.conversation, sent.message_id, true);
    const auto forwarded = client.forward_message(args.conversation, sent.message_id, args.conversation);
    if (!forwarded.ok || forwarded.forwarded_from_message_id != sent.message_id) {
        std::cerr << "desktop smoke: forward failed " << forwarded.error_code << " "
                  << forwarded.error_message << "\n";
        return 1;
    }
    smoke_store.apply_sent_message(args.conversation, forwarded);
    const auto actions_transcript = smoke_store.render_selected_transcript();
    if (actions_transcript.find("[reply_to=" + sent.message_id + "]") == std::string::npos
        || actions_transcript.find("[reactions=+1:1]") == std::string::npos
        || actions_transcript.find("[pinned]") == std::string::npos
        || actions_transcript.find("[forwarded_from=" + args.conversation + "/" + sent.message_id) == std::string::npos) {
        std::cerr << "desktop smoke: message actions store rendering failed\n";
        return 1;
    }
    std::cout << "desktop message actions smoke ok: reply=" << reply.message_id
              << " forward=" << forwarded.message_id
              << " reactions=" << reaction.reaction_summary << "\n";
    const auto server_search = client.search_messages("reply from Qt desktop smoke", "", 10);
    bool saw_server_search_result = false;
    for (const auto& result : server_search.results) {
        if (result.message_id == reply.message_id && result.conversation_id == args.conversation) {
            saw_server_search_result = true;
        }
    }
    if (!server_search.ok || !saw_server_search_result) {
        std::cerr << "desktop smoke: server message search failed "
                  << server_search.error_code << " " << server_search.error_message << "\n";
        return 1;
    }
    std::cout << "desktop server message search smoke ok: results="
              << server_search.results.size() << " hit=" << reply.message_id << "\n";
    const auto history_page = client.conversation_history_page(args.conversation, "", 2);
    if (!history_page.ok || history_page.conversations.empty()
        || history_page.conversations.front().messages.size() != 2
        || !history_page.conversations.front().has_more
        || history_page.conversations.front().next_before_message_id.empty()) {
        std::cerr << "desktop smoke: history page failed\n";
        return 1;
    }
    std::cout << "desktop history page smoke ok: messages="
              << history_page.conversations.front().messages.size()
              << " next_before=" << history_page.conversations.front().next_before_message_id << "\n";
    const auto incremental = client.conversation_sync_since(cursors);
    bool saw_sent_incremental = false;
    for (const auto& conversation : incremental.conversations) {
        for (const auto& message : conversation.messages) {
            if (message.message_id == sent.message_id) saw_sent_incremental = true;
        }
    }
    if (!incremental.ok || !saw_sent_incremental) {
        std::cerr << "desktop smoke: incremental sync missed " << sent.message_id << "\n";
        return 1;
    }
    std::cout << "desktop incremental smoke ok: message_id=" << sent.message_id << "\n";
    const auto devices = client.list_devices();
    if (!devices.ok || devices.devices.empty()) {
        std::cerr << "desktop smoke: device list failed " << devices.error_code << " "
                  << devices.error_message << "\n";
        return 1;
    }
    std::cout << "desktop devices smoke ok: devices=" << devices.devices.size()
              << " first=" << devices.devices.front().device_id << "\n";
    const auto profile = client.profile_get();
    if (!profile.ok || profile.user_id != login.user_id) {
        std::cerr << "desktop smoke: profile get failed " << profile.error_code << " "
                  << profile.error_message << "\n";
        return 1;
    }
    const auto updated_profile = client.profile_update("Alice Smoke");
    if (!updated_profile.ok || updated_profile.display_name != "Alice Smoke") {
        std::cerr << "desktop smoke: profile update failed " << updated_profile.error_code << " "
                  << updated_profile.error_message << "\n";
        return 1;
    }
    std::cout << "desktop profile smoke ok: user=" << updated_profile.user_id
              << " display=" << updated_profile.display_name << "\n";
    const auto search_before_contact = client.search_users("bob", 5);
    if (!search_before_contact.ok || search_before_contact.results.empty()
        || search_before_contact.results.front().user_id != "u_bob") {
        std::cerr << "desktop smoke: user search failed " << search_before_contact.error_code << " "
                  << search_before_contact.error_message << "\n";
        return 1;
    }
    std::cout << "desktop user search smoke ok: results="
              << search_before_contact.results.size()
              << " first=" << search_before_contact.results.front().user_id << "\n";
    const auto contacts_added = client.add_contact("u_bob");
    if (!contacts_added.ok || contacts_added.contacts.empty()) {
        std::cerr << "desktop smoke: contact add failed " << contacts_added.error_code << " "
                  << contacts_added.error_message << "\n";
        return 1;
    }
    const auto search_after_contact = client.search_users("bob", 5);
    if (!search_after_contact.ok || search_after_contact.results.empty()
        || !search_after_contact.results.front().is_contact) {
        std::cerr << "desktop smoke: user search contact flag failed\n";
        return 1;
    }
    const auto contacts_removed = client.remove_contact("u_bob");
    if (!contacts_removed.ok) {
        std::cerr << "desktop smoke: contact remove failed " << contacts_removed.error_code << " "
                  << contacts_removed.error_message << "\n";
        return 1;
    }
    std::cout << "desktop contacts smoke ok: added=u_bob remaining="
              << contacts_removed.contacts.size() << "\n";
    const auto group = client.create_conversation({"u_bob"}, "Qt Smoke Group");
    if (!group.ok || group.conversation.conversation_id.empty()
        || group.conversation.participant_user_ids.size() < 2) {
        std::cerr << "desktop smoke: group create failed " << group.error_code << " "
                  << group.error_message << "\n";
        return 1;
    }
    std::cout << "desktop group smoke ok: conversation_id="
              << group.conversation.conversation_id
              << " participants=" << group.conversation.participant_user_ids.size() << "\n";
    if (args.smoke_attachment) {
        const std::string attachment_body = "desktop attachment smoke bytes";
        std::vector<std::string> upload_stages;
        upload_stages.push_back("queued");
        upload_stages.push_back("uploading");
        const auto attached = client.send_attachment(
            args.conversation,
            "desktop attachment smoke",
            "desktop-smoke.txt",
            "text/plain",
            attachment_body
        );
        if (!attached.ok) {
            std::cerr << "desktop smoke: attachment send failed " << attached.error_code << " "
                      << attached.error_message << "\n";
            return 1;
        }
        upload_stages.push_back("uploaded");
        std::cout << "desktop attachment upload progress smoke ok: stages="
                  << upload_stages.front() << "," << upload_stages[1] << ","
                  << upload_stages.back() << " bytes=" << attachment_body.size() << "\n";
        std::vector<std::string> download_stages;
        download_stages.push_back("downloading");
        const auto fetched = client.fetch_attachment(attached.attachment_id);
        if (!fetched.ok || fetched.content != attachment_body) {
            std::cerr << "desktop smoke: attachment fetch mismatch\n";
            return 1;
        }
        download_stages.push_back("downloaded");
        if (!args.smoke_save_dir.empty()) {
            const std::string save_path = args.smoke_save_dir + "/desktop-smoke.txt";
            download_stages.push_back("saving");
            std::ofstream out(save_path, std::ios::binary | std::ios::trunc);
            out.write(fetched.content.data(), static_cast<std::streamsize>(fetched.content.size()));
            out.close();
            if (!out) {
                std::cerr << "desktop smoke: attachment save failed\n";
                return 1;
            }
            download_stages.push_back("saved");
            std::cout << "desktop attachment save smoke ok: path=" << save_path
                      << " bytes=" << fetched.content.size() << "\n";
        }
        std::cout << "desktop attachment download progress smoke ok: stages=";
        for (std::size_t i = 0; i < download_stages.size(); ++i) {
            if (i > 0) std::cout << ",";
            std::cout << download_stages[i];
        }
        std::cout << " bytes=" << fetched.content.size() << "\n";
        std::cout << "desktop attachment smoke ok: attachment_id="
                  << attached.attachment_id << " bytes=" << fetched.content.size() << "\n";
    }
    client.disconnect();
    return 0;
}

class DesktopWindow final : public QMainWindow {
    enum class DeviceAction { Revoke, Trust, Untrust };

public:
    explicit DesktopWindow(const Args& args, QWidget* parent = nullptr)
        : QMainWindow(parent), args_(args) {
        auto* root = new QWidget(this);
        auto* root_layout = new QVBoxLayout(root);

        auto* server_row = new QHBoxLayout();
        host_ = new QLineEdit(qstr(args.host), root);
        port_ = new QSpinBox(root);
        port_->setRange(1, 65535);
        port_->setValue(args.port);
        conversation_ = new QLineEdit(qstr(args.conversation), root);
        server_row->addWidget(new QLabel("Host", root));
        server_row->addWidget(host_);
        server_row->addWidget(new QLabel("Port", root));
        server_row->addWidget(port_);
        server_row->addWidget(new QLabel("Conversation", root));
        server_row->addWidget(conversation_);
        root_layout->addLayout(server_row);

        auto* login_row = new QHBoxLayout();
        user_ = new QLineEdit(qstr(args.user), root);
        password_ = new QLineEdit(qstr(args.password), root);
        password_->setEchoMode(QLineEdit::Password);
        display_name_ = new QLineEdit(qstr(args.display_name.empty() ? args.user : args.display_name), root);
        device_ = new QLineEdit(qstr(args.device), root);
        connect_ = new QPushButton("Connect", root);
        register_ = new QPushButton("Register", root);
        login_row->addWidget(new QLabel("User", root));
        login_row->addWidget(user_);
        login_row->addWidget(new QLabel("Password", root));
        login_row->addWidget(password_);
        login_row->addWidget(new QLabel("Display", root));
        login_row->addWidget(display_name_);
        login_row->addWidget(new QLabel("Device", root));
        login_row->addWidget(device_);
        login_row->addWidget(connect_);
        login_row->addWidget(register_);
        root_layout->addLayout(login_row);

        auto* profile_row = new QHBoxLayout();
        profile_display_name_ = new QLineEdit(root);
        profile_display_name_->setPlaceholderText("profile display name");
        refresh_profile_ = new QPushButton("Refresh Profile", root);
        save_profile_ = new QPushButton("Save Profile", root);
        profile_ = new QPlainTextEdit(root);
        profile_->setReadOnly(true);
        profile_->setMaximumHeight(72);
        profile_->setPlaceholderText("Profile appears here after connect.");
        set_profile_action_enabled(false);
        profile_row->addWidget(new QLabel("Profile", root));
        profile_row->addWidget(profile_display_name_, 1);
        profile_row->addWidget(refresh_profile_);
        profile_row->addWidget(save_profile_);
        root_layout->addLayout(profile_row);
        root_layout->addWidget(profile_);

        messages_ = new QTextBrowser(root);
        messages_->setReadOnly(true);
        messages_->setOpenLinks(false);
        messages_->setPlaceholderText("Connect to load recent messages. Incoming pushes appear here.");
        chat_filter_ = new QLineEdit(root);
        chat_filter_->setPlaceholderText("Filter chats by title, participant, message...");
        message_search_ = new QLineEdit(root);
        message_search_->setPlaceholderText("Search in selected conversation...");
        prev_match_ = new QPushButton("Prev", root);
        next_match_ = new QPushButton("Next", root);
        load_older_ = new QPushButton("Load Older", root);
        server_search_ = new QPushButton("Search Server", root);
        load_older_->setEnabled(false);
        server_search_->setEnabled(false);
        search_status_ = new QLabel("No search", root);
        message_search_results_ = new QPlainTextEdit(root);
        message_search_results_->setReadOnly(true);
        message_search_results_->setMaximumHeight(110);
        message_search_results_->setPlaceholderText("Server search results appear here.");
        auto* nav_row = new QHBoxLayout();
        nav_row->addWidget(new QLabel("Chats", root));
        nav_row->addWidget(chat_filter_, 1);
        nav_row->addWidget(new QLabel("Messages", root));
        nav_row->addWidget(message_search_, 1);
        nav_row->addWidget(prev_match_);
        nav_row->addWidget(next_match_);
        nav_row->addWidget(load_older_);
        nav_row->addWidget(server_search_);
        nav_row->addWidget(search_status_);
        root_layout->addLayout(nav_row);
        auto* content_row = new QHBoxLayout();
        conversations_ = new QListWidget(root);
        conversations_->setMinimumWidth(260);
        conversations_->setMaximumWidth(360);
        content_row->addWidget(conversations_);
        content_row->addWidget(messages_, 1);
        root_layout->addLayout(content_row, 1);
        root_layout->addWidget(message_search_results_);

        auto* send_row = new QHBoxLayout();
        composer_ = new QLineEdit(root);
        composer_->setPlaceholderText("Type a message...");
        send_ = new QPushButton("Send", root);
        attach_ = new QPushButton("Attach", root);
        send_->setEnabled(false);
        attach_->setEnabled(false);
        send_row->addWidget(composer_, 1);
        send_row->addWidget(attach_);
        send_row->addWidget(send_);
        root_layout->addLayout(send_row);

        auto* message_action_row = new QHBoxLayout();
        message_action_id_ = new QLineEdit(root);
        message_action_id_->setPlaceholderText("message_id");
        reaction_emoji_ = new QLineEdit("+1", root);
        reaction_emoji_->setMaximumWidth(80);
        reply_ = new QPushButton("Reply", root);
        forward_ = new QPushButton("Forward", root);
        react_ = new QPushButton("React", root);
        pin_ = new QPushButton("Pin", root);
        unpin_ = new QPushButton("Unpin", root);
        use_match_ = new QPushButton("Use Match", root);
        use_latest_ = new QPushButton("Use Latest", root);
        set_message_action_enabled(false);
        message_action_row->addWidget(new QLabel("Message Action", root));
        message_action_row->addWidget(message_action_id_, 1);
        message_action_row->addWidget(reaction_emoji_);
        message_action_row->addWidget(use_match_);
        message_action_row->addWidget(use_latest_);
        message_action_row->addWidget(reply_);
        message_action_row->addWidget(forward_);
        message_action_row->addWidget(react_);
        message_action_row->addWidget(pin_);
        message_action_row->addWidget(unpin_);
        root_layout->addLayout(message_action_row);

        auto* attachment_row = new QHBoxLayout();
        attachment_id_ = new QLineEdit(root);
        attachment_id_->setPlaceholderText("attachment_id to save");
        save_attachment_ = new QPushButton("Save Attachment", root);
        save_attachment_->setEnabled(false);
        attachment_row->addWidget(new QLabel("Attachment", root));
        attachment_row->addWidget(attachment_id_, 1);
        attachment_row->addWidget(save_attachment_);
        root_layout->addLayout(attachment_row);

        auto* transfer_row = new QHBoxLayout();
        transfer_status_ = new QLabel("Transfer idle", root);
        transfer_progress_ = new QProgressBar(root);
        transfer_progress_->setRange(0, 100);
        transfer_progress_->setValue(0);
        transfer_progress_->setTextVisible(true);
        transfer_row->addWidget(transfer_status_);
        transfer_row->addWidget(transfer_progress_, 1);
        root_layout->addLayout(transfer_row);

        auto* device_row = new QHBoxLayout();
        refresh_devices_ = new QPushButton("Refresh Devices", root);
        refresh_devices_->setEnabled(false);
        devices_ = new QPlainTextEdit(root);
        devices_->setReadOnly(true);
        devices_->setMaximumHeight(110);
        devices_->setPlaceholderText("Connected devices appear here.");
        device_row->addWidget(refresh_devices_);
        device_row->addWidget(devices_, 1);
        root_layout->addLayout(device_row);

        auto* device_action_row = new QHBoxLayout();
        device_action_id_ = new QLineEdit(root);
        device_action_id_->setPlaceholderText("device_id to manage");
        revoke_device_ = new QPushButton("Revoke", root);
        trust_device_ = new QPushButton("Trust", root);
        untrust_device_ = new QPushButton("Untrust", root);
        set_device_action_enabled(false);
        device_action_row->addWidget(new QLabel("Manage Device", root));
        device_action_row->addWidget(device_action_id_, 1);
        device_action_row->addWidget(revoke_device_);
        device_action_row->addWidget(trust_device_);
        device_action_row->addWidget(untrust_device_);
        root_layout->addLayout(device_action_row);

        auto* contacts_row = new QHBoxLayout();
        refresh_contacts_ = new QPushButton("Refresh Contacts", root);
        refresh_contacts_->setEnabled(false);
        contact_user_id_ = new QLineEdit(root);
        contact_user_id_->setPlaceholderText("user_id");
        add_contact_ = new QPushButton("Add Contact", root);
        remove_contact_ = new QPushButton("Remove Contact", root);
        contacts_ = new QPlainTextEdit(root);
        contacts_->setReadOnly(true);
        contacts_->setMaximumHeight(100);
        contacts_->setPlaceholderText("Contacts appear here.");
        set_contact_action_enabled(false);
        contacts_row->addWidget(refresh_contacts_);
        contacts_row->addWidget(contact_user_id_, 1);
        contacts_row->addWidget(add_contact_);
        contacts_row->addWidget(remove_contact_);
        root_layout->addLayout(contacts_row);
        root_layout->addWidget(contacts_);

        auto* user_search_row = new QHBoxLayout();
        user_search_query_ = new QLineEdit(root);
        user_search_query_->setPlaceholderText("search username/display/user_id");
        search_users_ = new QPushButton("Search Users", root);
        user_search_results_ = new QPlainTextEdit(root);
        user_search_results_->setReadOnly(true);
        user_search_results_->setMaximumHeight(100);
        user_search_results_->setPlaceholderText("User search results appear here.");
        set_user_search_enabled(false);
        user_search_row->addWidget(new QLabel("Find User", root));
        user_search_row->addWidget(user_search_query_, 1);
        user_search_row->addWidget(search_users_);
        root_layout->addLayout(user_search_row);
        root_layout->addWidget(user_search_results_);

        auto* group_row = new QHBoxLayout();
        group_title_ = new QLineEdit(root);
        group_title_->setPlaceholderText("new group title");
        group_participants_ = new QLineEdit(root);
        group_participants_->setPlaceholderText("participant user_ids comma-separated");
        create_group_ = new QPushButton("Create Group", root);
        create_group_->setEnabled(false);
        group_row->addWidget(new QLabel("Group", root));
        group_row->addWidget(group_title_, 1);
        group_row->addWidget(group_participants_, 1);
        group_row->addWidget(create_group_);
        root_layout->addLayout(group_row);

        auto* member_row = new QHBoxLayout();
        member_user_id_ = new QLineEdit(root);
        member_user_id_->setPlaceholderText("member user_id");
        add_member_ = new QPushButton("Add Member", root);
        remove_member_ = new QPushButton("Remove Member", root);
        set_group_action_enabled(false);
        member_row->addWidget(new QLabel("Selected Conversation Member", root));
        member_row->addWidget(member_user_id_, 1);
        member_row->addWidget(add_member_);
        member_row->addWidget(remove_member_);
        root_layout->addLayout(member_row);

        setCentralWidget(root);
        resize(980, 640);
        setWindowTitle("Telegram-like Desktop");
        statusBar()->showMessage("Disconnected");
        store_.set_selected_conversation(args.conversation);
        load_cache();
        render_store();

        QObject::connect(connect_, &QPushButton::clicked, [this] { connect_and_sync(); });
        QObject::connect(register_, &QPushButton::clicked, [this] { register_and_sync(); });
        QObject::connect(send_, &QPushButton::clicked, [this] { send_message(); });
        QObject::connect(attach_, &QPushButton::clicked, [this] { send_attachment(); });
        QObject::connect(reply_, &QPushButton::clicked, [this] { reply_message(); });
        QObject::connect(forward_, &QPushButton::clicked, [this] { forward_message(); });
        QObject::connect(react_, &QPushButton::clicked, [this] { react_to_message(); });
        QObject::connect(pin_, &QPushButton::clicked, [this] { pin_message(true); });
        QObject::connect(unpin_, &QPushButton::clicked, [this] { pin_message(false); });
        QObject::connect(use_match_, &QPushButton::clicked, [this] { use_focused_message_as_action_target(); });
        QObject::connect(use_latest_, &QPushButton::clicked, [this] { use_latest_message_as_action_target(); });
        QObject::connect(messages_, &QTextBrowser::anchorClicked, [this](const QUrl& url) {
            if (url.scheme() != "msg") return;
            const auto target = url.host().isEmpty() ? url.path().mid(1) : url.host();
            if (!target.isEmpty()) {
                message_action_id_->setText(target);
                statusBar()->showMessage("Selected message " + target);
            }
        });
        QObject::connect(save_attachment_, &QPushButton::clicked, [this] { save_attachment(); });
        QObject::connect(refresh_devices_, &QPushButton::clicked, [this] { refresh_devices(); });
        QObject::connect(refresh_profile_, &QPushButton::clicked, [this] { refresh_profile(); });
        QObject::connect(save_profile_, &QPushButton::clicked, [this] { save_profile(); });
        QObject::connect(revoke_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Revoke); });
        QObject::connect(trust_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Trust); });
        QObject::connect(untrust_device_, &QPushButton::clicked, [this] { manage_device(DeviceAction::Untrust); });
        QObject::connect(refresh_contacts_, &QPushButton::clicked, [this] { refresh_contacts(); });
        QObject::connect(add_contact_, &QPushButton::clicked, [this] { manage_contact(true); });
        QObject::connect(remove_contact_, &QPushButton::clicked, [this] { manage_contact(false); });
        QObject::connect(search_users_, &QPushButton::clicked, [this] { search_users(); });
        QObject::connect(create_group_, &QPushButton::clicked, [this] { create_group(); });
        QObject::connect(add_member_, &QPushButton::clicked, [this] { manage_group_member(true); });
        QObject::connect(remove_member_, &QPushButton::clicked, [this] { manage_group_member(false); });
        QObject::connect(chat_filter_, &QLineEdit::textChanged, [this] { render_conversation_list(); });
        QObject::connect(message_search_, &QLineEdit::textChanged, [this] {
            current_search_index_ = -1;
            refresh_message_search();
        });
        QObject::connect(prev_match_, &QPushButton::clicked, [this] { step_message_search(-1); });
        QObject::connect(next_match_, &QPushButton::clicked, [this] { step_message_search(1); });
        QObject::connect(load_older_, &QPushButton::clicked, [this] { load_older_history(); });
        QObject::connect(server_search_, &QPushButton::clicked, [this] { search_server_messages(); });
        QObject::connect(composer_, &QLineEdit::returnPressed, [this] { send_message(); });
        QObject::connect(conversations_, &QListWidget::itemClicked, [this](QListWidgetItem* item) {
            if (item == nullptr) return;
            const auto conversation_id = str(item->data(Qt::UserRole).toString());
            if (conversation_id.empty()) return;
            store_.set_selected_conversation(conversation_id);
            conversation_->setText(qstr(conversation_id));
            attachment_id_->setText(qstr(store_.latest_attachment_id(conversation_id)));
            message_action_id_->setText(qstr(store_.last_message_id(conversation_id)));
            current_search_index_ = -1;
            refresh_message_search();
            save_cache();
            render_store();
        });
    }

    ~DesktopWindow() override {
        shutting_down_ = true;
        if (client_) client_->disconnect();
    }

private:
    void append_line(const QString& line) {
        messages_->append(line.toHtmlEscaped());
    }

    void render_store() {
        const auto focused_id = focused_search_message_id();
        messages_->setHtml(qstr(store_.render_selected_timeline_html(str(message_search_->text().trimmed()), focused_id)));
        render_conversation_list();
        render_search_status();
        const auto summary = store_.render_conversation_summary();
        const auto selected = store_.selected_conversation_id();
        std::string status = "Connected";
        if (!selected.empty()) status += " | selected=" + selected;
        if (!summary.empty()) status += " | " + summary;
        statusBar()->showMessage(qstr(status));
    }

    void render_conversation_list() {
        conversations_->clear();
        const auto selected = store_.selected_conversation_id();
        const auto filter = str(chat_filter_->text().trimmed());
        int selected_row = -1;
        int row = 0;
        for (const auto& conversation : store_.filtered_conversations(filter)) {
            std::string label = conversation.conversation_id;
            if (!conversation.title.empty()) label = conversation.title + "  (" + conversation.conversation_id + ")";
            if (conversation.unread_count > 0) label += "  unread " + std::to_string(conversation.unread_count);
            if (!conversation.last_message_id.empty()) label += "\nlast " + conversation.last_message_id;
            auto* item = new QListWidgetItem(qstr(label));
            item->setData(Qt::UserRole, qstr(conversation.conversation_id));
            conversations_->addItem(item);
            if (conversation.conversation_id == selected) selected_row = row;
            ++row;
        }
        if (selected_row >= 0) {
            conversations_->setCurrentRow(selected_row);
        }
    }

    std::string focused_search_message_id() const {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty() || current_search_index_ < 0
            || current_search_index_ >= static_cast<int>(results.size())) {
            return {};
        }
        return results[static_cast<std::size_t>(current_search_index_)].message_id;
    }

    void refresh_message_search() {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty()) {
            current_search_index_ = -1;
        } else if (current_search_index_ < 0 || current_search_index_ >= static_cast<int>(results.size())) {
            current_search_index_ = 0;
        }
        render_store();
    }

    void step_message_search(int delta) {
        const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
        if (results.empty()) {
            current_search_index_ = -1;
            render_store();
            return;
        }
        if (current_search_index_ < 0) current_search_index_ = 0;
        current_search_index_ = (current_search_index_ + delta + static_cast<int>(results.size()))
            % static_cast<int>(results.size());
        const auto& focused = results[static_cast<std::size_t>(current_search_index_)];
        message_action_id_->setText(qstr(focused.message_id));
        render_store();
    }

    void use_focused_message_as_action_target() {
        auto focused = focused_search_message_id();
        if (focused.empty()) {
            const auto results = store_.search_selected_messages(str(message_search_->text().trimmed()));
            if (!results.empty()) focused = results.front().message_id;
        }
        if (!focused.empty()) {
            message_action_id_->setText(qstr(focused));
            statusBar()->showMessage("Selected message " + qstr(focused));
        }
    }

    void use_latest_message_as_action_target() {
        const auto conversation = str(conversation_->text().trimmed());
        if (conversation.empty()) return;
        const auto latest = store_.last_message_id(conversation);
        if (!latest.empty()) {
            message_action_id_->setText(qstr(latest));
            statusBar()->showMessage("Selected latest message " + qstr(latest));
        }
    }

    void render_search_status() {
        if (!search_status_) return;
        const auto query = str(message_search_->text().trimmed());
        const auto results = store_.search_selected_messages(query);
        if (query.empty()) {
            search_status_->setText("No search");
            return;
        }
        if (results.empty()) {
            search_status_->setText("0 matches");
            return;
        }
        const int visible_index = current_search_index_ < 0 ? 1 : current_search_index_ + 1;
        search_status_->setText(qstr(std::to_string(visible_index) + "/" + std::to_string(results.size())));
    }

    void load_older_history() {
        if (!client_) return;
        const auto conversation_id = str(conversation_->text().trimmed());
        if (conversation_id.empty()) return;
        const auto before = store_.history_next_before_message_id(conversation_id);
        load_older_->setEnabled(false);
        auto client = client_;
        std::thread([this, client, conversation_id, before] {
            const auto page = client->conversation_history_page(conversation_id, before, 25);
            QMetaObject::invokeMethod(this, [this, conversation_id, page] {
                if (shutting_down_) return;
                load_older_->setEnabled(true);
                if (!page.ok) {
                    append_line("[error] history page failed: " + qstr(page.error_code + " " + page.error_message));
                    return;
                }
                store_.apply_history_page(page);
                save_cache();
                render_store();
                statusBar()->showMessage("Loaded older history for " + qstr(conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void search_server_messages() {
        if (!client_) return;
        const auto query = str(message_search_->text().trimmed());
        if (query.empty()) return;
        const auto conversation_id = str(conversation_->text().trimmed());
        server_search_->setEnabled(false);
        auto client = client_;
        std::thread([this, client, query, conversation_id] {
            const auto result = client->search_messages(query, conversation_id, 20, 0);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                server_search_->setEnabled(true);
                render_server_message_search(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void render_server_message_search(const telegram_like::client::transport::MessageSearchResult& result) {
        if (!message_search_results_) return;
        if (!result.ok) {
            message_search_results_->setPlainText("[error] message search failed: " + qstr(result.error_code + " " + result.error_message));
            return;
        }
        QString text;
        for (const auto& entry : result.results) {
            text += qstr(entry.conversation_id + "  " + entry.message_id + "  " + entry.sender_user_id + "\n");
            text += qstr("  " + (entry.conversation_title.empty() ? std::string("(untitled)") : entry.conversation_title) + "\n");
            text += qstr("  " + entry.snippet + "\n");
            if (!entry.filename.empty()) {
                text += qstr("  attachment: " + entry.filename + "\n");
            }
            text += "\n";
        }
        if (text.isEmpty()) text = "(no server matches)";
        if (result.has_more) {
            text += qstr("more results at offset " + std::to_string(result.next_offset) + "\n");
        }
        message_search_results_->setPlainText(text);
        if (!result.results.empty()) {
            const auto& first = result.results.front();
            message_action_id_->setText(qstr(first.message_id));
            if (first.conversation_id != store_.selected_conversation_id()) {
                store_.set_selected_conversation(first.conversation_id);
                conversation_->setText(qstr(first.conversation_id));
                render_store();
            }
        }
    }

    void connect_and_sync() {
        authenticate_and_sync(false);
    }

    void register_and_sync() {
        authenticate_and_sync(true);
    }

    void authenticate_and_sync(bool create_account) {
        connect_->setEnabled(false);
        register_->setEnabled(false);
        send_->setEnabled(false);
        statusBar()->showMessage(create_account ? "Registering..." : "Connecting...");
        append_line(create_account ? "[system] registering" : "[system] connecting");

        const auto host = str(host_->text());
        const auto port = static_cast<unsigned short>(port_->value());
        const auto user = str(user_->text());
        const auto password = str(password_->text());
        const auto display_name = str(display_name_->text());
        const auto device = str(device_->text());
        const auto selected_conversation = str(conversation_->text());

        store_.set_selected_conversation(selected_conversation);
        load_cache();
        render_store();
        const auto cursors = store_.sync_cursors();

        std::thread([this, host, port, user, password, display_name, device, cursors, create_account] {
            auto next_client = std::make_shared<ControlPlaneClient>();
            if (!next_client->connect(host, port)) {
                post_error("connect failed");
                return;
            }
            const auto auth = create_account
                ? next_client->register_user(user, password, display_name, device)
                : next_client->login(user, password, device);
            if (!auth.ok) {
                post_error(std::string(create_account ? "register failed: " : "login failed: ")
                           + auth.error_code + " " + auth.error_message);
                return;
            }
            next_client->set_push_handler([this](const std::string& type, const std::string& envelope) {
                QMetaObject::invokeMethod(this, [this, type, envelope] {
                    if (shutting_down_) return;
                    store_.apply_push(type, envelope);
                    save_cache();
                    render_store();
                }, Qt::QueuedConnection);
            });
            next_client->start_heartbeat(10000);
            const auto sync = next_client->conversation_sync_since(cursors);
            if (!sync.ok) {
                post_error("sync failed: " + sync.error_code + " " + sync.error_message);
                return;
            }

            QMetaObject::invokeMethod(this, [this, auth, sync, cursors, client = std::move(next_client), create_account] {
                if (shutting_down_) return;
                client_ = client;
                store_.set_current_user(auth.user_id);
                if (cursors.empty()) {
                    store_.apply_sync(sync);
                } else {
                    store_.apply_incremental_sync(sync);
                }
                save_cache();
                render_store();
                connect_->setEnabled(true);
                register_->setEnabled(true);
                send_->setEnabled(true);
                attach_->setEnabled(true);
                load_older_->setEnabled(true);
                server_search_->setEnabled(true);
                set_message_action_enabled(true);
                save_attachment_->setEnabled(true);
                set_profile_action_enabled(true);
                refresh_devices_->setEnabled(true);
                set_device_action_enabled(true);
                refresh_contacts_->setEnabled(true);
                set_contact_action_enabled(true);
                set_user_search_enabled(true);
                set_group_action_enabled(true);
                statusBar()->showMessage(qstr(std::string(create_account ? "Registered as " : "Connected as ") + auth.user_id));
                refresh_profile();
                refresh_devices();
                refresh_contacts();
            }, Qt::QueuedConnection);
        }).detach();
    }

    void send_message() {
        if (!client_ || composer_->text().trimmed().isEmpty()) return;
        const auto text = str(composer_->text());
        const auto conversation = str(conversation_->text());
        const auto local_message_id = store_.add_pending_message(conversation, text);
        composer_->clear();
        save_cache();
        render_store();
        send_->setEnabled(false);

        auto client = client_;
        std::thread([this, client, conversation, text, local_message_id] {
            const auto sent = client->send_message(conversation, text);
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                send_->setEnabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Send failed");
                } else {
                    store_.resolve_pending_message(conversation, local_message_id, sent);
                    if (!sent.attachment_id.empty()) {
                        attachment_id_->setText(qstr(sent.attachment_id));
                    }
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Sent " + qstr(sent.message_id));
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void reply_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()
            || composer_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto reply_to = str(message_action_id_->text().trimmed());
        const auto text = str(composer_->text());
        const auto local_message_id = store_.add_pending_message(conversation, text);
        composer_->clear();
        save_cache();
        render_store();
        set_message_action_enabled(false);

        auto client = client_;
        std::thread([this, client, conversation, reply_to, text, local_message_id] {
            const auto sent = client->reply_message(conversation, reply_to, text);
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    statusBar()->showMessage("Reply failed");
                    return;
                }
                store_.resolve_pending_message(conversation, local_message_id, sent);
                message_action_id_->setText(qstr(sent.message_id));
                save_cache();
                render_store();
                statusBar()->showMessage("Replied " + qstr(sent.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void forward_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id] {
            const auto sent = client->forward_message(conversation, message_id, conversation);
            QMetaObject::invokeMethod(this, [this, conversation, sent] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!sent.ok) {
                    append_line("[error] forward failed: " + qstr(sent.error_code + " " + sent.error_message));
                    return;
                }
                store_.apply_sent_message(conversation, sent);
                message_action_id_->setText(qstr(sent.message_id));
                save_cache();
                render_store();
                statusBar()->showMessage("Forwarded " + qstr(sent.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void react_to_message() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()
            || reaction_emoji_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        const auto emoji = str(reaction_emoji_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, emoji] {
            const auto result = client->toggle_reaction(conversation, message_id, emoji);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] reaction failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_reaction_summary(result.conversation_id, result.message_id, result.reaction_summary);
                save_cache();
                render_store();
                statusBar()->showMessage("Reaction updated " + qstr(result.message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void pin_message(bool pinned) {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, pinned] {
            const auto result = client->set_message_pin(conversation, message_id, pinned);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] pin failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_pin_state(result.conversation_id, result.message_id, result.pinned);
                save_cache();
                render_store();
                statusBar()->showMessage(result.pinned ? "Pinned" : "Unpinned");
            }, Qt::QueuedConnection);
        }).detach();
    }

    void send_attachment() {
        if (!client_) return;
        const QString path = QFileDialog::getOpenFileName(this, "Attach file");
        if (path.isEmpty()) return;
        set_transfer_progress("Reading attachment", 10);
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) {
            set_transfer_progress("Attachment read failed", 0);
            append_line("[error] attachment open failed");
            return;
        }
        const QByteArray bytes = file.readAll();
        if (bytes.size() > 1'048'576) {
            set_transfer_progress("Attachment too large", 0);
            append_line("[error] attachment too large for current 1 MB cap");
            return;
        }
        const QFileInfo info(path);
        const auto conversation = str(conversation_->text());
        const auto caption = str(composer_->text());
        const auto filename = str(info.fileName());
        const auto mime_type = guess_mime_type(info);
        const std::string content(bytes.constData(), static_cast<std::size_t>(bytes.size()));
        const auto local_message_id = store_.add_pending_attachment_message(
            conversation,
            caption,
            filename,
            mime_type,
            static_cast<long long>(content.size())
        );
        composer_->clear();
        save_cache();
        render_store();
        send_->setEnabled(false);
        attach_->setEnabled(false);
        set_transfer_progress("Uploading " + filename, 35);

        auto client = client_;
        std::thread([this, client, conversation, caption, filename, mime_type, content, local_message_id] {
            const auto sent = client->send_attachment(
                conversation,
                caption,
                filename,
                mime_type,
                content
            );
            QMetaObject::invokeMethod(this, [this, conversation, local_message_id, sent] {
                if (shutting_down_) return;
                send_->setEnabled(true);
                attach_->setEnabled(true);
                if (!sent.ok) {
                    store_.fail_pending_message(conversation, local_message_id, sent.error_code + " " + sent.error_message);
                    save_cache();
                    render_store();
                    set_transfer_progress("Upload failed", 0);
                    append_line("[error] attachment send failed: " + qstr(sent.error_code + " " + sent.error_message));
                } else {
                    store_.resolve_pending_message(conversation, local_message_id, sent);
                    save_cache();
                    render_store();
                    set_transfer_progress("Uploaded " + sent.filename, 100);
                    statusBar()->showMessage("Attached " + qstr(sent.attachment_id));
                }
            }, Qt::QueuedConnection);
        }).detach();
    }

    void save_attachment() {
        if (!client_) return;
        const auto attachment_id = str(attachment_id_->text().trimmed());
        if (attachment_id.empty()) return;
        const auto conversation_id = str(conversation_->text());
        const auto known_filename = store_.attachment_filename(conversation_id, attachment_id);
        const QString path = QFileDialog::getSaveFileName(
            this,
            "Save attachment",
            qstr(known_filename.empty() ? attachment_id + ".bin" : known_filename)
        );
        if (path.isEmpty()) return;
        save_attachment_->setEnabled(false);
        set_transfer_progress("Downloading " + attachment_id, 35);

        auto client = client_;
        const auto save_path = str(path);
        std::thread([this, client, attachment_id, save_path] {
            const auto fetched = client->fetch_attachment(attachment_id);
            QMetaObject::invokeMethod(this, [this, fetched, save_path] {
                if (shutting_down_) return;
                save_attachment_->setEnabled(true);
                if (!fetched.ok) {
                    set_transfer_progress("Download failed", 0);
                    append_line("[error] attachment fetch failed: " + qstr(fetched.error_code + " " + fetched.error_message));
                    return;
                }
                set_transfer_progress("Saving " + fetched.filename, 75);
                QFile file(qstr(save_path));
                if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                    set_transfer_progress("Save failed", 0);
                    append_line("[error] attachment save failed");
                    return;
                }
                const QByteArray bytes(fetched.content.data(), static_cast<int>(fetched.content.size()));
                if (file.write(bytes) != bytes.size()) {
                    set_transfer_progress("Save incomplete", 0);
                    append_line("[error] attachment write incomplete");
                    return;
                }
                file.close();
                set_transfer_progress("Saved " + fetched.filename, 100);
                statusBar()->showMessage("Saved attachment " + qstr(fetched.attachment_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_profile() {
        if (!client_) return;
        set_profile_action_enabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->profile_get();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_profile_action_enabled(true);
                if (!result.ok) {
                    profile_->setPlainText("[error] profile load failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_profile(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void save_profile() {
        if (!client_ || profile_display_name_->text().trimmed().isEmpty()) return;
        const auto display_name = str(profile_display_name_->text().trimmed());
        set_profile_action_enabled(false);
        auto client = client_;
        std::thread([this, client, display_name] {
            const auto result = client->profile_update(display_name);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_profile_action_enabled(true);
                if (!result.ok) {
                    profile_->setPlainText("[error] profile save failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_profile(result);
                statusBar()->showMessage("Saved profile for " + qstr(result.user_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_devices() {
        if (!client_) return;
        refresh_devices_->setEnabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->list_devices();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                refresh_devices_->setEnabled(true);
                if (!result.ok) {
                    devices_->setPlainText("[error] device list failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_devices(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_device(DeviceAction action) {
        if (!client_ || device_action_id_->text().trimmed().isEmpty()) return;
        const auto device_id = str(device_action_id_->text().trimmed());
        if (action == DeviceAction::Revoke) {
            const auto answer = QMessageBox::question(
                this,
                "Revoke device",
                "Revoke device " + qstr(device_id) + "?",
                QMessageBox::Yes | QMessageBox::No,
                QMessageBox::No);
            if (answer != QMessageBox::Yes) return;
        }
        set_device_action_enabled(false);
        auto client = client_;
        std::thread([this, client, device_id, action] {
            telegram_like::client::transport::DeviceListResult result;
            if (action == DeviceAction::Revoke) {
                result = client->revoke_device(device_id);
            } else {
                result = client->update_device_trust(device_id, action == DeviceAction::Trust);
            }
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_device_action_enabled(true);
                if (!result.ok) {
                    devices_->setPlainText("[error] device action failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_devices(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void refresh_contacts() {
        if (!client_) return;
        refresh_contacts_->setEnabled(false);
        auto client = client_;
        std::thread([this, client] {
            const auto result = client->list_contacts();
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                refresh_contacts_->setEnabled(true);
                if (!result.ok) {
                    contacts_->setPlainText("[error] contact list failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_contacts(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_contact(bool add) {
        if (!client_ || contact_user_id_->text().trimmed().isEmpty()) return;
        const auto user_id = str(contact_user_id_->text().trimmed());
        set_contact_action_enabled(false);
        auto client = client_;
        std::thread([this, client, user_id, add] {
            const auto result = add ? client->add_contact(user_id) : client->remove_contact(user_id);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_contact_action_enabled(true);
                if (!result.ok) {
                    contacts_->setPlainText("[error] contact action failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_contacts(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    void search_users() {
        if (!client_ || user_search_query_->text().trimmed().isEmpty()) return;
        const auto query = str(user_search_query_->text().trimmed());
        set_user_search_enabled(false);
        auto client = client_;
        std::thread([this, client, query] {
            const auto result = client->search_users(query, 20);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_user_search_enabled(true);
                if (!result.ok) {
                    user_search_results_->setPlainText("[error] user search failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                render_user_search(result);
            }, Qt::QueuedConnection);
        }).detach();
    }

    std::vector<std::string> parse_user_ids(const QString& raw) const {
        std::vector<std::string> ids;
        for (const auto& part : raw.split(',')) {
            const auto id = str(part.trimmed());
            if (!id.empty()) ids.push_back(id);
        }
        return ids;
    }

    void create_group() {
        if (!client_) return;
        const auto participants = parse_user_ids(group_participants_->text());
        if (participants.empty()) return;
        const auto title = str(group_title_->text().trimmed());
        set_group_action_enabled(false);
        auto client = client_;
        std::thread([this, client, participants, title] {
            const auto result = client->create_conversation(participants, title);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_group_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] group create failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                apply_conversation_action(result);
                statusBar()->showMessage("Created group " + qstr(result.conversation.conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void manage_group_member(bool add) {
        if (!client_ || member_user_id_->text().trimmed().isEmpty()) return;
        const auto selected = str(conversation_->text().trimmed());
        if (selected.empty()) return;
        const auto user_id = str(member_user_id_->text().trimmed());
        set_group_action_enabled(false);
        auto client = client_;
        std::thread([this, client, selected, user_id, add] {
            const auto result = add
                ? client->add_conversation_participant(selected, user_id)
                : client->remove_conversation_participant(selected, user_id);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_group_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] group member update failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                apply_conversation_action(result);
                statusBar()->showMessage("Updated group " + qstr(result.conversation.conversation_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void apply_conversation_action(const telegram_like::client::transport::ConversationActionResult& result) {
        telegram_like::client::transport::SyncResult sync;
        sync.ok = true;
        sync.conversations.push_back(result.conversation);
        store_.apply_incremental_sync(sync);
        store_.set_selected_conversation(result.conversation.conversation_id);
        conversation_->setText(qstr(result.conversation.conversation_id));
        save_cache();
        render_store();
    }

    void render_devices(const telegram_like::client::transport::DeviceListResult& result) {
        QString text;
        for (const auto& device : result.devices) {
            text += qstr(device.device_id + "  " + device.label + "  " + device.platform);
            text += device.active ? "  online" : "  offline";
            text += device.trusted ? "  trusted" : "  untrusted";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no devices)";
        devices_->setPlainText(text);
    }

    void render_profile(const telegram_like::client::transport::ProfileResult& result) {
        profile_display_name_->setText(qstr(result.display_name));
        profile_->setPlainText(qstr(
            result.user_id + "  @" + result.username + "\n"
            + "display: " + result.display_name
        ));
    }

    void render_contacts(const telegram_like::client::transport::ContactListResult& result) {
        QString text;
        for (const auto& contact : result.contacts) {
            text += qstr(contact.user_id + "  " + contact.display_name);
            text += contact.online ? "  online" : "  offline";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no contacts)";
        contacts_->setPlainText(text);
    }

    void render_user_search(const telegram_like::client::transport::UserSearchResult& result) {
        QString text;
        for (const auto& user : result.results) {
            text += qstr(user.user_id + "  @" + user.username + "  " + user.display_name);
            text += user.online ? "  online" : "  offline";
            text += user.is_contact ? "  contact" : "  not-contact";
            text += "\n";
        }
        if (text.isEmpty()) text = "(no users found)";
        user_search_results_->setPlainText(text);
    }

    void set_device_action_enabled(bool enabled) {
        if (revoke_device_) revoke_device_->setEnabled(enabled);
        if (trust_device_) trust_device_->setEnabled(enabled);
        if (untrust_device_) untrust_device_->setEnabled(enabled);
    }

    void set_contact_action_enabled(bool enabled) {
        if (add_contact_) add_contact_->setEnabled(enabled);
        if (remove_contact_) remove_contact_->setEnabled(enabled);
    }

    void set_profile_action_enabled(bool enabled) {
        if (refresh_profile_) refresh_profile_->setEnabled(enabled);
        if (save_profile_) save_profile_->setEnabled(enabled);
    }

    void set_user_search_enabled(bool enabled) {
        if (search_users_) search_users_->setEnabled(enabled);
    }

    void set_group_action_enabled(bool enabled) {
        if (create_group_) create_group_->setEnabled(enabled);
        if (add_member_) add_member_->setEnabled(enabled);
        if (remove_member_) remove_member_->setEnabled(enabled);
    }

    void set_message_action_enabled(bool enabled) {
        if (reply_) reply_->setEnabled(enabled);
        if (forward_) forward_->setEnabled(enabled);
        if (react_) react_->setEnabled(enabled);
        if (pin_) pin_->setEnabled(enabled);
        if (unpin_) unpin_->setEnabled(enabled);
        if (use_match_) use_match_->setEnabled(enabled);
        if (use_latest_) use_latest_->setEnabled(enabled);
    }

    void set_transfer_progress(const std::string& label, int percent) {
        if (transfer_status_) transfer_status_->setText(qstr(label));
        if (transfer_progress_) transfer_progress_->setValue(percent);
    }

    void post_error(std::string message) {
        QMetaObject::invokeMethod(this, [this, message = std::move(message)] {
            if (shutting_down_) return;
            append_line("[error] " + qstr(message));
            connect_->setEnabled(true);
            register_->setEnabled(true);
            send_->setEnabled(client_ != nullptr);
            attach_->setEnabled(client_ != nullptr);
            load_older_->setEnabled(client_ != nullptr);
            server_search_->setEnabled(client_ != nullptr);
            set_message_action_enabled(client_ != nullptr);
            save_attachment_->setEnabled(client_ != nullptr);
            set_profile_action_enabled(client_ != nullptr);
            refresh_devices_->setEnabled(client_ != nullptr);
            set_device_action_enabled(client_ != nullptr);
            refresh_contacts_->setEnabled(client_ != nullptr);
            set_contact_action_enabled(client_ != nullptr);
            set_user_search_enabled(client_ != nullptr);
            set_group_action_enabled(client_ != nullptr);
            statusBar()->showMessage("Error");
        }, Qt::QueuedConnection);
    }

    void load_cache() {
        if (args_.cache_file.empty()) return;
        std::string error;
        if (!store_.load_from_file(args_.cache_file, &error)) {
            if (error != "open_for_read_failed") {
                append_line("[cache] load failed: " + qstr(error));
            }
            return;
        }
        store_.set_selected_conversation(str(conversation_->text()));
    }

    void save_cache() {
        if (args_.cache_file.empty()) return;
        std::string error;
        if (!store_.save_to_file(args_.cache_file, &error)) {
            append_line("[cache] save failed: " + qstr(error));
        }
    }

    Args args_;
    QLineEdit* host_ {nullptr};
    QSpinBox* port_ {nullptr};
    QLineEdit* conversation_ {nullptr};
    QLineEdit* user_ {nullptr};
    QLineEdit* password_ {nullptr};
    QLineEdit* display_name_ {nullptr};
    QLineEdit* device_ {nullptr};
    QPushButton* connect_ {nullptr};
    QPushButton* register_ {nullptr};
    QLineEdit* chat_filter_ {nullptr};
    QLineEdit* message_search_ {nullptr};
    QPushButton* prev_match_ {nullptr};
    QPushButton* next_match_ {nullptr};
    QPushButton* load_older_ {nullptr};
    QPushButton* server_search_ {nullptr};
    QLabel* search_status_ {nullptr};
    QPlainTextEdit* message_search_results_ {nullptr};
    QLineEdit* profile_display_name_ {nullptr};
    QPushButton* refresh_profile_ {nullptr};
    QPushButton* save_profile_ {nullptr};
    QPlainTextEdit* profile_ {nullptr};
    QListWidget* conversations_ {nullptr};
    QTextBrowser* messages_ {nullptr};
    QLineEdit* composer_ {nullptr};
    QPushButton* attach_ {nullptr};
    QLineEdit* message_action_id_ {nullptr};
    QLineEdit* reaction_emoji_ {nullptr};
    QPushButton* reply_ {nullptr};
    QPushButton* forward_ {nullptr};
    QPushButton* react_ {nullptr};
    QPushButton* pin_ {nullptr};
    QPushButton* unpin_ {nullptr};
    QPushButton* use_match_ {nullptr};
    QPushButton* use_latest_ {nullptr};
    QLineEdit* attachment_id_ {nullptr};
    QPushButton* save_attachment_ {nullptr};
    QLabel* transfer_status_ {nullptr};
    QProgressBar* transfer_progress_ {nullptr};
    QPushButton* send_ {nullptr};
    QPushButton* refresh_devices_ {nullptr};
    QPlainTextEdit* devices_ {nullptr};
    QLineEdit* device_action_id_ {nullptr};
    QPushButton* revoke_device_ {nullptr};
    QPushButton* trust_device_ {nullptr};
    QPushButton* untrust_device_ {nullptr};
    QPushButton* refresh_contacts_ {nullptr};
    QPlainTextEdit* contacts_ {nullptr};
    QLineEdit* contact_user_id_ {nullptr};
    QPushButton* add_contact_ {nullptr};
    QPushButton* remove_contact_ {nullptr};
    QLineEdit* user_search_query_ {nullptr};
    QPushButton* search_users_ {nullptr};
    QPlainTextEdit* user_search_results_ {nullptr};
    QLineEdit* group_title_ {nullptr};
    QLineEdit* group_participants_ {nullptr};
    QPushButton* create_group_ {nullptr};
    QLineEdit* member_user_id_ {nullptr};
    QPushButton* add_member_ {nullptr};
    QPushButton* remove_member_ {nullptr};
    std::shared_ptr<ControlPlaneClient> client_;
    telegram_like::client::app_desktop::DesktopChatStore store_;
    int current_search_index_ {-1};
    std::atomic<bool> shutting_down_ {false};
};

}  // namespace

int main(int argc, char** argv) {
    Args args;
    if (!parse_args(argc, argv, args)) {
        std::cerr << "usage: app_desktop [--smoke] [--user alice] [--password alice_pw] "
                     "[--display-name Alice] [--device dev_alice_qt] [--host 127.0.0.1] [--port 8787] "
                     "[--conversation conv_alice_bob] [--cache-file path]\n";
        return 2;
    }

    if (args.smoke) {
        return run_smoke(args);
    }

    QApplication app(argc, argv);
    DesktopWindow window(args);
    window.show();
    return app.exec();
}
