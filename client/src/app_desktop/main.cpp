#include "app_desktop/bubble_list_view.h"
#include "app_desktop/design_tokens.h"
#include "app_desktop/desktop_chat_store.h"
#include "app_desktop/typing_indicator.h"
#include "transport/control_plane_client.h"

#include <QDateTime>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPropertyAnimation>
#include <QSet>
#include <QTimer>

#include <QAction>
#include <QApplication>
#include <QCheckBox>
#include <QFile>
#include <QComboBox>
#include <QDialog>
#include <QFileDialog>
#include <QFileInfo>
#include <QFont>
#include <QFrame>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMainWindow>
#include <QMenu>
#include <QMetaObject>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QPainter>
#include <QPixmap>
#include <QRadioButton>
#include <QScrollArea>
#include <QSettings>
#include <QSizePolicy>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QStatusBar>
#include <QString>
#include <QToolButton>
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
    bool tls = false;
    bool tls_insecure = false;
    std::string tls_server_name;
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
        } else if (arg == "--tls") {
            out.tls = true;
        } else if (arg == "--tls-insecure") {
            out.tls = true;
            out.tls_insecure = true;
        } else if (arg == "--tls-server-name") {
            const char* v = next("--tls-server-name");
            if (!v) return false;
            out.tls_server_name = v;
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
    const bool connected = args.tls
        ? client.connect_tls(args.host, args.port, args.tls_insecure, args.tls_server_name)
        : client.connect(args.host, args.port);
    if (!connected) {
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
        // ---- create every widget first; layout is assembled below ----
        host_ = new QLineEdit(qstr(args.host));
        port_ = new QSpinBox();
        port_->setRange(1, 65535);
        port_->setValue(args.port);
        conversation_ = new QLineEdit(qstr(args.conversation));
        tls_ = new QCheckBox("TLS");
        tls_->setChecked(args.tls);
        tls_insecure_ = new QCheckBox("Dev insecure");
        tls_insecure_->setChecked(args.tls_insecure);

        user_ = new QLineEdit(qstr(args.user));
        password_ = new QLineEdit(qstr(args.password));
        password_->setEchoMode(QLineEdit::Password);
        display_name_ = new QLineEdit(qstr(args.display_name.empty() ? args.user : args.display_name));
        device_ = new QLineEdit(qstr(args.device));
        connect_ = new QPushButton("Connect");
        connect_->setObjectName("primary");
        register_ = new QPushButton("Register");

        profile_display_name_ = new QLineEdit();
        profile_display_name_->setPlaceholderText("profile display name");
        refresh_profile_ = new QPushButton("Refresh");
        save_profile_ = new QPushButton("Save");
        profile_ = new QPlainTextEdit();
        profile_->setReadOnly(true);
        profile_->setMaximumHeight(72);
        profile_->setPlaceholderText("Profile appears here after connect.");
        set_profile_action_enabled(false);

        // M138: BubbleListView replaces the QTextBrowser-based timeline.
        // Bubbles, ticks, gradients, avatars, reply quotes, forwarded
        // headers, reaction chips, pinned markers + the right-click
        // context menu are all painted by BubbleDelegate, so we no longer
        // depend on Qt rich text supporting things it doesn't.
        messages_ = new telegram_like::client::app_desktop::BubbleListView();

        chat_filter_ = new QLineEdit();
        chat_filter_->setPlaceholderText("Search chats");
        chat_filter_->setClearButtonEnabled(true);

        message_search_ = new QLineEdit();
        message_search_->setPlaceholderText("Search in this chat");
        message_search_->setClearButtonEnabled(true);
        prev_match_ = new QPushButton("‹");
        next_match_ = new QPushButton("›");
        prev_match_->setMaximumWidth(28);
        next_match_->setMaximumWidth(28);
        load_older_ = new QPushButton("Older");
        server_search_ = new QPushButton("Server");
        load_older_->setEnabled(false);
        server_search_->setEnabled(false);
        search_status_ = new QLabel("No search");
        search_status_->setObjectName("searchStatus");
        message_search_results_ = new QPlainTextEdit();
        message_search_results_->setReadOnly(true);
        message_search_results_->setMaximumHeight(96);
        message_search_results_->setPlaceholderText("Server search results appear here.");

        conversations_ = new QListWidget();
        conversations_->setObjectName("chatList");
        conversations_->setMinimumWidth(260);
        conversations_->setSpacing(2);

        composer_ = new QLineEdit();
        composer_->setPlaceholderText("Message");
        send_ = new QPushButton("Send");
        send_->setObjectName("primary");
        attach_ = new QPushButton("Attach");
        send_->setEnabled(false);
        attach_->setEnabled(false);

        message_action_id_ = new QLineEdit();
        message_action_id_->setPlaceholderText("message_id");
        reaction_emoji_ = new QLineEdit("+1");
        reaction_emoji_->setMaximumWidth(80);
        reply_ = new QPushButton("Reply");
        forward_ = new QPushButton("Forward");
        react_ = new QPushButton("React");
        pin_ = new QPushButton("Pin");
        unpin_ = new QPushButton("Unpin");
        edit_ = new QPushButton("Edit");
        delete_ = new QPushButton("Delete");
        use_match_ = new QPushButton("Use Match");
        use_latest_ = new QPushButton("Use Latest");
        set_message_action_enabled(false);

        attachment_id_ = new QLineEdit();
        attachment_id_->setPlaceholderText("attachment_id to save");
        save_attachment_ = new QPushButton("Save Attachment");
        save_attachment_->setEnabled(false);

        transfer_status_ = new QLabel("Transfer idle");
        transfer_progress_ = new QProgressBar();
        transfer_progress_->setRange(0, 100);
        transfer_progress_->setValue(0);
        transfer_progress_->setTextVisible(true);

        refresh_devices_ = new QPushButton("Refresh Devices");
        refresh_devices_->setEnabled(false);
        devices_ = new QPlainTextEdit();
        devices_->setReadOnly(true);
        devices_->setMaximumHeight(110);
        devices_->setPlaceholderText("Connected devices appear here.");

        device_action_id_ = new QLineEdit();
        device_action_id_->setPlaceholderText("device_id to manage");
        revoke_device_ = new QPushButton("Revoke");
        trust_device_ = new QPushButton("Trust");
        untrust_device_ = new QPushButton("Untrust");
        set_device_action_enabled(false);

        refresh_contacts_ = new QPushButton("Refresh Contacts");
        refresh_contacts_->setEnabled(false);
        contact_user_id_ = new QLineEdit();
        contact_user_id_->setPlaceholderText("user_id");
        add_contact_ = new QPushButton("Add");
        remove_contact_ = new QPushButton("Remove");
        contacts_ = new QPlainTextEdit();
        contacts_->setReadOnly(true);
        contacts_->setMaximumHeight(100);
        contacts_->setPlaceholderText("Contacts appear here.");
        set_contact_action_enabled(false);

        user_search_query_ = new QLineEdit();
        user_search_query_->setPlaceholderText("search username/display/user_id");
        search_users_ = new QPushButton("Search Users");
        user_search_results_ = new QPlainTextEdit();
        user_search_results_->setReadOnly(true);
        user_search_results_->setMaximumHeight(100);
        user_search_results_->setPlaceholderText("User search results appear here.");
        set_user_search_enabled(false);

        group_title_ = new QLineEdit();
        group_title_->setPlaceholderText("new group title");
        group_participants_ = new QLineEdit();
        group_participants_->setPlaceholderText("participant user_ids comma-separated");
        create_group_ = new QPushButton("Create Group");
        create_group_->setEnabled(false);

        member_user_id_ = new QLineEdit();
        member_user_id_->setPlaceholderText("member user_id");
        add_member_ = new QPushButton("Add Member");
        remove_member_ = new QPushButton("Remove Member");
        set_group_action_enabled(false);

        // ---- M128: voice/video call panel ----
        call_callee_user_ = new QLineEdit();
        call_callee_user_->setPlaceholderText("callee user_id (e.g. u_bob)");
        call_callee_device_ = new QLineEdit();
        call_callee_device_->setPlaceholderText("callee device_id (e.g. dev_bob_win)");
        call_kind_ = new QComboBox();
        call_kind_->addItem("audio");
        call_kind_->addItem("video");
        call_id_input_ = new QLineEdit();
        call_id_input_->setPlaceholderText("call_id (auto-filled after invite)");
        call_invite_ = new QPushButton("Invite");
        call_accept_ = new QPushButton("Accept");
        call_decline_ = new QPushButton("Decline");
        call_end_ = new QPushButton("End");
        call_log_ = new QPlainTextEdit();
        call_log_->setReadOnly(true);
        call_log_->setMaximumHeight(140);
        call_log_->setPlaceholderText("Call FSM transitions appear here.");
        set_call_action_enabled(false);

        // ---- M108: remote-control panel ----
        remote_target_device_ = new QLineEdit();
        remote_target_device_->setPlaceholderText("target device_id (e.g. dev_bob_win)");
        remote_invite_ = new QPushButton("Invite");
        remote_session_id_input_ = new QLineEdit();
        remote_session_id_input_->setPlaceholderText("remote_session_id (from invite or push)");
        remote_approve_ = new QPushButton("Approve");
        remote_reject_ = new QPushButton("Reject");
        remote_cancel_ = new QPushButton("Cancel");
        remote_terminate_ = new QPushButton("Terminate");
        remote_rendezvous_ = new QPushButton("Rendezvous");
        remote_log_ = new QPlainTextEdit();
        remote_log_->setReadOnly(true);
        remote_log_->setMaximumHeight(140);
        remote_log_->setPlaceholderText("Remote-control RPC results and rendezvous info appear here.");
        set_remote_action_enabled(false);

        chat_header_title_ = new QLabel("No chat selected");
        chat_header_title_->setObjectName("chatHeaderTitle");
        chat_header_subtitle_ = new QLabel("");
        chat_header_subtitle_->setObjectName("chatHeaderSubtitle");

        // ---- sidebar (left) ----
        auto* sidebar = new QWidget();
        sidebar->setObjectName("sidebar");
        auto* sidebar_layout = new QVBoxLayout(sidebar);
        sidebar_layout->setContentsMargins(0, 0, 0, 0);
        sidebar_layout->setSpacing(0);
        auto* sidebar_search_wrap = new QWidget();
        sidebar_search_wrap->setObjectName("sidebarSearch");
        auto* sidebar_search_layout = new QHBoxLayout(sidebar_search_wrap);
        sidebar_search_layout->setContentsMargins(10, 10, 10, 10);
        sidebar_search_layout->addWidget(chat_filter_);
        sidebar_layout->addWidget(sidebar_search_wrap);
        sidebar_layout->addWidget(conversations_, 1);
        toggle_details_ = new QPushButton("Settings ▸");
        toggle_details_->setObjectName("ghost");
        auto* sidebar_footer_wrap = new QWidget();
        sidebar_footer_wrap->setObjectName("sidebarFooter");
        auto* sidebar_footer_layout = new QHBoxLayout(sidebar_footer_wrap);
        sidebar_footer_layout->setContentsMargins(10, 8, 10, 8);
        sidebar_footer_layout->addWidget(toggle_details_, 1);
        sidebar_layout->addWidget(sidebar_footer_wrap);

        // ---- center pane ----
        auto* center = new QWidget();
        center->setObjectName("centerPane");
        auto* center_layout = new QVBoxLayout(center);
        center_layout->setContentsMargins(0, 0, 0, 0);
        center_layout->setSpacing(0);
        // chat header
        auto* chat_header = new QWidget();
        chat_header->setObjectName("chatHeader");
        auto* chat_header_layout = new QHBoxLayout(chat_header);
        chat_header_layout->setContentsMargins(16, 10, 16, 10);
        auto* header_titles = new QVBoxLayout();
        header_titles->setSpacing(0);
        header_titles->addWidget(chat_header_title_);
        // M140: subtitle row carries the static "online · participants"
        // text + the animated typing indicator. The indicator hides itself
        // when inactive so the subtitle reflows seamlessly.
        auto* subtitle_row = new QHBoxLayout();
        subtitle_row->setSpacing(8);
        subtitle_row->setContentsMargins(0, 0, 0, 0);
        subtitle_row->addWidget(chat_header_subtitle_);
        typing_indicator_ = new telegram_like::client::app_desktop::TypingIndicator();
        subtitle_row->addWidget(typing_indicator_);
        subtitle_row->addStretch(1);
        header_titles->addLayout(subtitle_row);
        chat_header_layout->addLayout(header_titles, 1);
        // M145: chat info button — opens a non-modal dialog with the
        // conversation summary (title, participants, pinned messages,
        // attachment count). Sits next to load_older / server_search so
        // the header reads left-to-right as identity → load → search → info.
        chat_info_btn_ = new QToolButton();
        chat_info_btn_->setObjectName("chatInfoBtn");
        chat_info_btn_->setText(QString::fromUtf8("\xe2\x84\xb9"));  // ℹ
        chat_info_btn_->setToolTip(QStringLiteral("Chat info"));
        chat_info_btn_->setCursor(Qt::PointingHandCursor);
        chat_header_layout->addWidget(chat_info_btn_);
        chat_header_layout->addWidget(load_older_);
        chat_header_layout->addWidget(server_search_);
        center_layout->addWidget(chat_header);
        // in-chat search row (under header)
        auto* search_row_wrap = new QWidget();
        search_row_wrap->setObjectName("inChatSearch");
        auto* search_row = new QHBoxLayout(search_row_wrap);
        search_row->setContentsMargins(16, 6, 16, 6);
        search_row->addWidget(message_search_, 1);
        search_row->addWidget(prev_match_);
        search_row->addWidget(next_match_);
        search_row->addWidget(search_status_);
        center_layout->addWidget(search_row_wrap);
        // M144: Pin message top strip — sits above the bubble list and
        // surfaces the most-recent pinned message snippet. Click jumps to
        // the message in-line. Hidden entirely when nothing is pinned so
        // the chat area gets the full vertical space.
        pin_bar_ = new QPushButton();
        pin_bar_->setObjectName("pinBar");
        pin_bar_->setVisible(false);
        pin_bar_->setCursor(Qt::PointingHandCursor);
        pin_bar_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        pin_bar_->setMinimumHeight(36);
        pin_bar_->setStyleSheet(
            "QPushButton#pinBar { text-align:left; padding:6px 12px;"
            " border:none; background:transparent; }");
        center_layout->addWidget(pin_bar_);
        // timeline
        center_layout->addWidget(messages_, 1);
        // server search result panel (collapsible feel)
        center_layout->addWidget(message_search_results_);
        // transfer status
        auto* transfer_wrap = new QWidget();
        auto* transfer_row = new QHBoxLayout(transfer_wrap);
        transfer_row->setContentsMargins(16, 4, 16, 4);
        transfer_row->addWidget(transfer_status_);
        transfer_row->addWidget(transfer_progress_, 1);
        center_layout->addWidget(transfer_wrap);
        // composer
        auto* composer_wrap = new QWidget();
        composer_wrap->setObjectName("composer");
        auto* send_row = new QHBoxLayout(composer_wrap);
        send_row->setContentsMargins(16, 10, 16, 12);
        send_row->setSpacing(8);
        send_row->addWidget(attach_);
        send_row->addWidget(composer_, 1);
        send_row->addWidget(send_);
        center_layout->addWidget(composer_wrap);
        // message-action row (advanced; stays visible under composer because smoke + power users use it)
        auto* message_action_wrap = new QWidget();
        message_action_wrap->setObjectName("messageActions");
        auto* message_action_row = new QHBoxLayout(message_action_wrap);
        message_action_row->setContentsMargins(16, 6, 16, 8);
        message_action_row->addWidget(new QLabel("Action"));
        message_action_row->addWidget(message_action_id_, 1);
        message_action_row->addWidget(reaction_emoji_);
        message_action_row->addWidget(use_match_);
        message_action_row->addWidget(use_latest_);
        message_action_row->addWidget(reply_);
        message_action_row->addWidget(forward_);
        message_action_row->addWidget(react_);
        message_action_row->addWidget(pin_);
        message_action_row->addWidget(unpin_);
        message_action_row->addWidget(edit_);
        message_action_row->addWidget(delete_);
        center_layout->addWidget(message_action_wrap);

        // ---- details panel (right, collapsible) ----
        details_panel_ = new QScrollArea();
        details_panel_->setObjectName("detailsPanel");
        details_panel_->setWidgetResizable(true);
        details_panel_->setFrameShape(QFrame::NoFrame);
        auto* details_inner = new QWidget();
        auto* details_root_layout = new QVBoxLayout(details_inner);
        details_root_layout->setContentsMargins(0, 0, 0, 0);
        details_root_layout->setSpacing(0);

        // Settings header bar
        auto* settings_header = new QWidget();
        settings_header->setObjectName("settingsHeader");
        auto* settings_header_layout = new QHBoxLayout(settings_header);
        settings_header_layout->setContentsMargins(16, 12, 12, 12);
        auto* settings_title = new QLabel("Settings");
        settings_title->setObjectName("settingsTitle");
        settings_header_layout->addWidget(settings_title, 1);
        auto* settings_close = new QToolButton();
        settings_close->setObjectName("settingsClose");
        settings_close->setText("✕");
        settings_close->setToolTip("Close settings");
        settings_header_layout->addWidget(settings_close);
        details_root_layout->addWidget(settings_header);

        // body: nav (left) + stacked pages (right)
        auto* body_wrap = new QWidget();
        auto* body_layout = new QHBoxLayout(body_wrap);
        body_layout->setContentsMargins(0, 0, 0, 0);
        body_layout->setSpacing(0);

        settings_nav_ = new QListWidget();
        settings_nav_->setObjectName("settingsNav");
        settings_nav_->setMinimumWidth(150);
        settings_nav_->setMaximumWidth(170);
        settings_nav_->setFrameShape(QFrame::NoFrame);
        settings_nav_->setSpacing(2);
        // M139: Telegram-style nav — each item gets a leading unicode glyph
        // so the column reads as an icon list rather than a plain text
        // list. Glyphs come from common Unicode planes; no external icon
        // assets needed. New "Appearance" entry hosts the light/dark
        // toggle below.
        struct NavEntry { const char* glyph; const char* label; };
        constexpr NavEntry nav_entries[] = {
            {"\xf0\x9f\x91\xa4", "Profile"},      // 👤
            {"\xf0\x9f\x94\x90", "Account"},      // 🔐
            {"\xf0\x9f\x8e\xa8", "Appearance"},   // 🎨  (M139)
            {"\xf0\x9f\x94\x97", "Connection"},   // 🔗
            {"\xf0\x9f\x92\xbb", "Devices"},      // 💻
            {"\xf0\x9f\x91\xa5", "Contacts"},     // 👥
            {"\xf0\x9f\x94\x8e", "Find Users"},   // 🔎
            {"\xf0\x9f\x91\xa5", "Groups"},       // 👥
            {"\xf0\x9f\x93\x8e", "Attachments"},  // 📎
            {"\xf0\x9f\x96\xa5\xef\xb8\x8f", "Remote"}, // 🖥️
            {"\xf0\x9f\x93\x9e", "Call"},         // 📞
        };
        for (const auto& entry : nav_entries) {
            const QString text = QString::fromUtf8(entry.glyph)
                + QStringLiteral("   ")
                + QString::fromUtf8(entry.label);
            settings_nav_->addItem(text);
        }
        body_layout->addWidget(settings_nav_);

        settings_pages_ = new QStackedWidget();
        settings_pages_->setObjectName("settingsPages");

        auto make_page = [](const char* title, const char* subtitle, QLayout* body) -> QWidget* {
            auto* page = new QWidget();
            auto* layout = new QVBoxLayout(page);
            layout->setContentsMargins(20, 18, 20, 18);
            layout->setSpacing(12);
            auto* heading = new QLabel(title);
            heading->setObjectName("pageHeading");
            layout->addWidget(heading);
            if (subtitle && *subtitle) {
                auto* sub = new QLabel(subtitle);
                sub->setObjectName("pageSubtitle");
                sub->setWordWrap(true);
                layout->addWidget(sub);
            }
            auto* container = new QWidget();
            container->setLayout(body);
            layout->addWidget(container);
            layout->addStretch(1);
            return page;
        };

        // === Profile page (with avatar) ===
        avatar_label_ = new QLabel();
        avatar_label_->setObjectName("profileAvatar");
        avatar_label_->setFixedSize(96, 96);
        avatar_label_->setAlignment(Qt::AlignCenter);
        update_avatar_pixmap(args.user, args.display_name.empty() ? args.user : args.display_name);

        profile_identity_label_ = new QLabel("Not connected");
        profile_identity_label_->setObjectName("profileIdentity");
        profile_identity_label_->setWordWrap(true);

        auto* profile_body = new QVBoxLayout();
        profile_body->setSpacing(10);
        auto* profile_top = new QHBoxLayout();
        profile_top->setSpacing(14);
        profile_top->addWidget(avatar_label_);
        auto* profile_top_text = new QVBoxLayout();
        profile_top_text->addWidget(profile_identity_label_);
        profile_top_text->addStretch(1);
        profile_top->addLayout(profile_top_text, 1);
        profile_body->addLayout(profile_top);
        profile_body->addWidget(new QLabel("Display name"));
        auto* prof_form = new QHBoxLayout();
        prof_form->addWidget(profile_display_name_, 1);
        prof_form->addWidget(refresh_profile_);
        prof_form->addWidget(save_profile_);
        profile_body->addLayout(prof_form);
        profile_body->addWidget(new QLabel("Server profile snapshot"));
        profile_body->addWidget(profile_);
        settings_pages_->addWidget(
            make_page("Profile", "Edit how others see you on this server.", profile_body));

        // === Account page ===
        auto* account_body = new QVBoxLayout();
        account_body->setSpacing(10);
        auto* acc_user_lab = new QLabel("Username");
        acc_user_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_user_lab);
        account_body->addWidget(user_);
        auto* acc_pwd_lab = new QLabel("Password");
        acc_pwd_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_pwd_lab);
        account_body->addWidget(password_);
        auto* acc_disp_lab = new QLabel("Display name (used at register)");
        acc_disp_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_disp_lab);
        account_body->addWidget(display_name_);
        auto* acc_dev_lab = new QLabel("Device id");
        acc_dev_lab->setObjectName("fieldLabel");
        account_body->addWidget(acc_dev_lab);
        account_body->addWidget(device_);
        auto* acc_btns = new QHBoxLayout();
        acc_btns->addWidget(connect_);
        acc_btns->addWidget(register_);
        acc_btns->addStretch(1);
        account_body->addLayout(acc_btns);
        settings_pages_->addWidget(
            make_page("Account", "Sign in or create a new account on this server.", account_body));

        // === Appearance page (M139) — light/dark theme + cosmetic notes ===
        // Telegram desktop's appearance section gives the user a visible
        // toggle for the theme; we match that via two QRadioButton choices
        // backed by a re-application of telegram_stylesheet() and a fresh
        // bubble palette push. The choice persists in QSettings under
        // "appearance/dark_theme" so subsequent launches start in the
        // last-selected mode without needing the env var.
        auto* appearance_body = new QVBoxLayout();
        appearance_body->setSpacing(10);
        auto* appearance_label = new QLabel("Theme");
        appearance_label->setObjectName("fieldLabel");
        appearance_body->addWidget(appearance_label);
        appearance_light_ = new QRadioButton("Light");
        appearance_dark_  = new QRadioButton("Dark");
        appearance_light_->setChecked(!telegram_like::client::app_desktop::design::is_dark_theme());
        appearance_dark_->setChecked(telegram_like::client::app_desktop::design::is_dark_theme());
        appearance_body->addWidget(appearance_light_);
        appearance_body->addWidget(appearance_dark_);
        auto* appearance_hint = new QLabel(
            "Light is the Telegram-Web-Z baseline; Dark mirrors the desktop \"Night\" palette. "
            "Changes apply immediately and are saved to your local settings file.");
        appearance_hint->setObjectName("pageSubtitle");
        appearance_hint->setWordWrap(true);
        appearance_body->addWidget(appearance_hint);
        settings_pages_->addWidget(
            make_page("Appearance", "Pick light or dark for the chat surface.", appearance_body));

        // === Connection page ===
        auto* connection_body = new QVBoxLayout();
        connection_body->setSpacing(10);
        auto* conn_host_lab = new QLabel("Host");
        conn_host_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_host_lab);
        auto* conn_host_row = new QHBoxLayout();
        conn_host_row->addWidget(host_, 1);
        conn_host_row->addWidget(new QLabel("Port"));
        conn_host_row->addWidget(port_);
        connection_body->addLayout(conn_host_row);
        auto* conn_tls_lab = new QLabel("Transport security");
        conn_tls_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_tls_lab);
        auto* conn_tls_row = new QHBoxLayout();
        conn_tls_row->addWidget(tls_);
        conn_tls_row->addWidget(tls_insecure_);
        conn_tls_row->addStretch(1);
        connection_body->addLayout(conn_tls_row);
        auto* conn_conv_lab = new QLabel("Default conversation");
        conn_conv_lab->setObjectName("fieldLabel");
        connection_body->addWidget(conn_conv_lab);
        connection_body->addWidget(conversation_);
        settings_pages_->addWidget(
            make_page("Connection", "Where to connect and how to secure the link.", connection_body));

        // === Devices page ===
        auto* devices_body = new QVBoxLayout();
        devices_body->setSpacing(10);
        auto* dev_top = new QHBoxLayout();
        dev_top->addWidget(refresh_devices_);
        dev_top->addStretch(1);
        devices_body->addLayout(dev_top);
        devices_body->addWidget(devices_);
        auto* dev_action_lab = new QLabel("Manage device");
        dev_action_lab->setObjectName("fieldLabel");
        devices_body->addWidget(dev_action_lab);
        devices_body->addWidget(device_action_id_);
        auto* dev_btns = new QHBoxLayout();
        dev_btns->addWidget(revoke_device_);
        dev_btns->addWidget(trust_device_);
        dev_btns->addWidget(untrust_device_);
        dev_btns->addStretch(1);
        devices_body->addLayout(dev_btns);
        settings_pages_->addWidget(
            make_page("Devices", "Sessions signed in to this account. Revoke or trust each device.", devices_body));

        // === Contacts page ===
        auto* contacts_body = new QVBoxLayout();
        contacts_body->setSpacing(10);
        auto* con_top = new QHBoxLayout();
        con_top->addWidget(refresh_contacts_);
        con_top->addStretch(1);
        contacts_body->addLayout(con_top);
        auto* con_id_lab = new QLabel("Contact user_id");
        con_id_lab->setObjectName("fieldLabel");
        contacts_body->addWidget(con_id_lab);
        contacts_body->addWidget(contact_user_id_);
        auto* con_btns = new QHBoxLayout();
        con_btns->addWidget(add_contact_);
        con_btns->addWidget(remove_contact_);
        con_btns->addStretch(1);
        contacts_body->addLayout(con_btns);
        contacts_body->addWidget(contacts_);
        settings_pages_->addWidget(
            make_page("Contacts", "Your saved contacts and their online state.", contacts_body));

        // === Find Users page ===
        auto* find_body = new QVBoxLayout();
        find_body->setSpacing(10);
        auto* find_lab = new QLabel("Search query");
        find_lab->setObjectName("fieldLabel");
        find_body->addWidget(find_lab);
        auto* find_row = new QHBoxLayout();
        find_row->addWidget(user_search_query_, 1);
        find_row->addWidget(search_users_);
        find_body->addLayout(find_row);
        find_body->addWidget(user_search_results_);
        settings_pages_->addWidget(
            make_page("Find Users", "Search by username, display name or user_id.", find_body));

        // === Groups page ===
        auto* groups_body = new QVBoxLayout();
        groups_body->setSpacing(10);
        auto* grp_title_lab = new QLabel("New group");
        grp_title_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_title_lab);
        groups_body->addWidget(group_title_);
        auto* grp_part_lab = new QLabel("Initial participants (comma-separated user_ids)");
        grp_part_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_part_lab);
        groups_body->addWidget(group_participants_);
        auto* grp_create_row = new QHBoxLayout();
        grp_create_row->addWidget(create_group_);
        grp_create_row->addStretch(1);
        groups_body->addLayout(grp_create_row);
        auto* grp_member_lab = new QLabel("Add or remove a member from the selected chat");
        grp_member_lab->setObjectName("fieldLabel");
        groups_body->addWidget(grp_member_lab);
        groups_body->addWidget(member_user_id_);
        auto* grp_member_btns = new QHBoxLayout();
        grp_member_btns->addWidget(add_member_);
        grp_member_btns->addWidget(remove_member_);
        grp_member_btns->addStretch(1);
        groups_body->addLayout(grp_member_btns);
        settings_pages_->addWidget(
            make_page("Groups", "Create new groups and manage selected chat membership.", groups_body));

        // === Attachments page ===
        auto* attach_body = new QVBoxLayout();
        attach_body->setSpacing(10);
        auto* att_lab = new QLabel("Attachment id");
        att_lab->setObjectName("fieldLabel");
        attach_body->addWidget(att_lab);
        attach_body->addWidget(attachment_id_);
        auto* att_btns = new QHBoxLayout();
        att_btns->addWidget(save_attachment_);
        att_btns->addStretch(1);
        attach_body->addLayout(att_btns);
        settings_pages_->addWidget(
            make_page("Attachments", "Save received attachments by id to disk.", attach_body));

        // === Remote-control page (M108) ===
        auto* remote_body = new QVBoxLayout();
        remote_body->setSpacing(10);
        auto* remote_invite_lab = new QLabel("Invite a target device into a remote session");
        remote_invite_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_invite_lab);
        remote_body->addWidget(remote_target_device_);
        auto* remote_invite_row = new QHBoxLayout();
        remote_invite_row->addWidget(remote_invite_);
        remote_invite_row->addStretch(1);
        remote_body->addLayout(remote_invite_row);
        auto* remote_session_lab = new QLabel(
            "Existing remote_session_id (received via push or copied from invite)");
        remote_session_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_session_lab);
        remote_body->addWidget(remote_session_id_input_);
        auto* remote_btns = new QHBoxLayout();
        remote_btns->addWidget(remote_approve_);
        remote_btns->addWidget(remote_reject_);
        remote_btns->addWidget(remote_cancel_);
        remote_btns->addWidget(remote_terminate_);
        remote_btns->addWidget(remote_rendezvous_);
        remote_btns->addStretch(1);
        remote_body->addLayout(remote_btns);
        auto* remote_log_lab = new QLabel("RPC results");
        remote_log_lab->setObjectName("fieldLabel");
        remote_body->addWidget(remote_log_lab);
        remote_body->addWidget(remote_log_);
        settings_pages_->addWidget(
            make_page(
                "Remote",
                "Invite, approve, terminate and discover relay info for remote-control sessions.",
                remote_body));

        // === Call page (M128) ===
        auto* call_body = new QVBoxLayout();
        call_body->setSpacing(10);
        auto* call_callee_lab = new QLabel("Place a call");
        call_callee_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_callee_lab);
        call_body->addWidget(call_callee_user_);
        call_body->addWidget(call_callee_device_);
        auto* call_kind_row = new QHBoxLayout();
        call_kind_row->addWidget(call_kind_);
        call_kind_row->addWidget(call_invite_);
        call_kind_row->addStretch(1);
        call_body->addLayout(call_kind_row);
        auto* call_id_lab = new QLabel("Active call_id");
        call_id_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_id_lab);
        call_body->addWidget(call_id_input_);
        auto* call_btns = new QHBoxLayout();
        call_btns->addWidget(call_accept_);
        call_btns->addWidget(call_decline_);
        call_btns->addWidget(call_end_);
        call_btns->addStretch(1);
        call_body->addLayout(call_btns);
        auto* call_log_lab = new QLabel("FSM log");
        call_log_lab->setObjectName("fieldLabel");
        call_body->addWidget(call_log_lab);
        call_body->addWidget(call_log_);
        settings_pages_->addWidget(
            make_page(
                "Call",
                "Voice/video call invite/accept/decline/end. Per-call AES-256-GCM key minted on accept.",
                call_body));

        body_layout->addWidget(settings_pages_, 1);
        details_root_layout->addWidget(body_wrap, 1);

        QObject::connect(settings_nav_, &QListWidget::currentRowChanged,
                         [this](int row) {
                             if (row >= 0) settings_pages_->setCurrentIndex(row);
                         });
        QObject::connect(settings_close, &QToolButton::clicked,
                         [this] { toggle_details_panel(); });
        settings_nav_->setCurrentRow(0);

        details_panel_->setWidget(details_inner);
        details_panel_->setMinimumWidth(420);
        details_panel_->setVisible(false);

        // ---- compose splitter ----
        auto* splitter = new QSplitter(Qt::Horizontal);
        splitter->setObjectName("mainSplitter");
        splitter->addWidget(sidebar);
        splitter->addWidget(center);
        splitter->addWidget(details_panel_);
        splitter->setStretchFactor(0, 0);
        splitter->setStretchFactor(1, 1);
        splitter->setStretchFactor(2, 0);
        splitter->setSizes({320, 700, 360});
        splitter->setChildrenCollapsible(false);

        setCentralWidget(splitter);
        resize(1200, 760);
        setWindowTitle("Telegram-like Desktop");
        setStyleSheet(telegram_stylesheet());
        statusBar()->showMessage("Disconnected");
        store_.set_selected_conversation(args.conversation);
        load_cache();
        update_chat_header();
        render_store();

        // M140 demo hook: TELEGRAM_LIKE_DEMO_TYPING=1 spins up the typing
        // indicator with a fake peer so the animation is visible without
        // a real backend pulse. Real fanout (TYPING_START/TYPING_STOP) is
        // a separate milestone — this primitive is the UI half.
        if (typing_indicator_ != nullptr) {
            const char* demo = std::getenv("TELEGRAM_LIKE_DEMO_TYPING");
            if (demo != nullptr && demo[0] == '1') {
                typing_indicator_->setActive(QStringLiteral("u_bob"), true);
            }
        }

        // M139: appearance toggle — flip the active theme, repaint every
        // surface (QSS for widgets + bubble palette for the message view)
        // and persist the choice so the next launch picks the same mode.
        auto apply_theme = [this](bool dark) {
            namespace dt = telegram_like::client::app_desktop::design;
            dt::set_active_theme(dark);
            if (auto* app = qobject_cast<QApplication*>(QCoreApplication::instance())) {
                app->setStyleSheet(telegram_stylesheet());
            }
            QSettings().setValue(QStringLiteral("appearance/dark_theme"), dark);
            render_store();
        };
        QObject::connect(appearance_light_, &QRadioButton::toggled,
            [this, apply_theme](bool checked) { if (checked) apply_theme(false); });
        QObject::connect(appearance_dark_, &QRadioButton::toggled,
            [this, apply_theme](bool checked) { if (checked) apply_theme(true); });
        // M144: clicking the pin bar focuses the pinned message — same
        // mechanism as in-chat search "Use Match" so the bubble scrolls
        // into view + the focused outline lights up.
        QObject::connect(pin_bar_, &QPushButton::clicked, [this] {
            if (pin_bar_target_id_.isEmpty() || messages_ == nullptr) return;
            messages_->setSearchHighlight(message_search_->text().trimmed(),
                                          pin_bar_target_id_);
        });
        // M147: composer typing → debounced TYPING_PULSE(true). Only fires
        // once every 2s so a fast typist doesn't generate a flood; the
        // indicator on the receiving side decays 5s after the last
        // inbound pulse via typing_decay_timer_.
        typing_decay_timer_ = new QTimer(this);
        typing_decay_timer_->setInterval(5000);
        typing_decay_timer_->setSingleShot(true);
        QObject::connect(typing_decay_timer_, &QTimer::timeout, [this] {
            if (typing_indicator_ != nullptr) {
                typing_indicator_->setActive(QString(), false);
            }
        });
        QObject::connect(composer_, &QLineEdit::textEdited, [this](const QString& text) {
            if (!client_ || text.isEmpty()) return;
            const auto conv = store_.selected_conversation_id();
            if (conv.empty()) return;
            const qint64 now = QDateTime::currentMSecsSinceEpoch();
            if (now - last_typing_sent_ms_ < 2000) return;
            last_typing_sent_ms_ = now;
            auto client = client_;
            std::thread([client, conv] {
                (void)client->send_typing_pulse(conv, true);
            }).detach();
        });
        // M145: chat info button opens a non-modal dialog summarising the
        // selected conversation. Constructed on each click so the
        // participant + pinned + attachment lists reflect the latest sync.
        QObject::connect(chat_info_btn_, &QToolButton::clicked, [this] {
            show_chat_info_dialog();
        });

        QObject::connect(connect_, &QPushButton::clicked, [this] { connect_and_sync(); });
        QObject::connect(register_, &QPushButton::clicked, [this] { register_and_sync(); });
        QObject::connect(send_, &QPushButton::clicked, [this] { send_message(); });
        QObject::connect(attach_, &QPushButton::clicked, [this] { send_attachment(); });
        QObject::connect(reply_, &QPushButton::clicked, [this] { reply_message(); });
        QObject::connect(forward_, &QPushButton::clicked, [this] { forward_message(); });
        QObject::connect(react_, &QPushButton::clicked, [this] { react_to_message(); });
        QObject::connect(pin_, &QPushButton::clicked, [this] { pin_message(true); });
        QObject::connect(unpin_, &QPushButton::clicked, [this] { pin_message(false); });
        QObject::connect(edit_, &QPushButton::clicked, [this] { edit_message_action(); });
        QObject::connect(delete_, &QPushButton::clicked, [this] { delete_message_action(); });
        QObject::connect(use_match_, &QPushButton::clicked, [this] { use_focused_message_as_action_target(); });
        QObject::connect(use_latest_, &QPushButton::clicked, [this] { use_latest_message_as_action_target(); });
        // M138: double-click a bubble to focus it as the current message
        // action target (used by the bottom-bar Reply/Forward/etc. fallback
        // controls, while the right-click context menu is the primary UX).
        QObject::connect(messages_,
            &telegram_like::client::app_desktop::BubbleListView::messageActivated,
            [this](const QString& message_id) {
                if (message_id.isEmpty()) return;
                message_action_id_->setText(message_id);
                statusBar()->showMessage("Selected message " + message_id, 2000);
            });
        QObject::connect(messages_,
            &telegram_like::client::app_desktop::BubbleListView::messageContextMenuRequested,
            [this](const QString& message_id, const QPoint& globalPos) {
                if (message_id.isEmpty()) return;
                message_action_id_->setText(message_id);
                QMenu menu(this);
                menu.addAction("Reply",   [this] { reply_message(); });
                menu.addAction("Forward", [this] { forward_message(); });
                menu.addAction("React",   [this] { react_to_message(); });
                menu.addSeparator();
                menu.addAction("Pin",   [this] { pin_message(true);  });
                menu.addAction("Unpin", [this] { pin_message(false); });
                menu.addSeparator();
                menu.addAction("Edit",   [this] { edit_message_action(); });
                menu.addAction("Delete", [this] { delete_message_action(); });
                menu.exec(globalPos);
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
        QObject::connect(remote_invite_, &QPushButton::clicked, [this] { remote_invite_action(); });
        QObject::connect(remote_approve_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Approve); });
        QObject::connect(remote_reject_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Reject); });
        QObject::connect(remote_cancel_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Cancel); });
        QObject::connect(remote_terminate_, &QPushButton::clicked, [this] { remote_terminal_action(RemoteOp::Terminate); });
        QObject::connect(remote_rendezvous_, &QPushButton::clicked, [this] { remote_rendezvous_action(); });
        QObject::connect(call_invite_, &QPushButton::clicked, [this] { call_invite_action(); });
        QObject::connect(call_accept_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::Accept); });
        QObject::connect(call_decline_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::Decline); });
        QObject::connect(call_end_, &QPushButton::clicked, [this] { call_terminal_action(CallOp::End); });
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
            update_chat_header();
            save_cache();
            render_store();
        });
        QObject::connect(toggle_details_, &QPushButton::clicked, [this] { toggle_details_panel(); });
    }

    ~DesktopWindow() override {
        shutting_down_ = true;
        if (client_) client_->disconnect();
    }

private:
    void append_line(const QString& line) {
        // M138: BubbleListView only renders messages, not log/error lines.
        // System info (errors, transfer progress, debug crumbs) used to be
        // appended into the chat area as plain text — that polluted the
        // bubble list. Route them to the status bar instead so they show
        // briefly without breaking the timeline.
        statusBar()->showMessage(line, 5000);
    }

    static QString telegram_stylesheet() {
        // M125 introduced design_tokens.h; M135 finishes the migration —
        // every QSS color now reads from the active theme so dark mode
        // toggling (TELEGRAM_LIKE_THEME=dark env var) actually changes
        // every surface instead of a leaky half-themed window.
        namespace dt = telegram_like::client::app_desktop::design;
        const auto& t = dt::active_theme();
        QString css = QString::fromUtf8(R"(
            QMainWindow, QWidget { background:{app_background}; color:{text_primary}; font-family:{font_stack}; font-size:{font_px}px; }
            QSplitter#mainSplitter::handle { background:{splitter}; width:1px; }
            QWidget#sidebar { background:{surface}; border-right:1px solid {border}; }
            QWidget#sidebarSearch { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QWidget#sidebarFooter { background:{surface_muted}; border-top:1px solid {border_subtle}; }
            QListWidget#chatList { background:{surface}; border:none; padding:6px 4px; }
            QListWidget#chatList::item { padding:10px 12px; border-radius:8px; margin:1px 4px; color:{text_primary}; }
            QListWidget#chatList::item:selected { background:{selection_tint}; color:{text_primary}; }
            QListWidget#chatList::item:hover { background:{hover}; }
            QWidget#centerPane { background:{chat_area}; }
            QWidget#chatHeader { background:{surface}; border-bottom:1px solid {border}; }
            QLabel#chatHeaderTitle { font-weight:600; font-size:15px; color:{text_primary}; }
            QLabel#chatHeaderSubtitle { font-size:11px; color:{text_muted}; }
            QWidget#inChatSearch { background:{in_chat_search_bg}; border-bottom:1px solid {border}; }
            QLabel#searchStatus { color:{text_muted}; font-size:11px; padding-left:6px; }
            QTextBrowser { background:{chat_area}; border:none; color:{text_primary}; }
            QWidget#composer { background:{surface}; border-top:1px solid {border}; }
            QWidget#messageActions { background:{secondary_header_tint}; border-top:1px solid {border_subtle}; }
            QScrollArea#detailsPanel { background:{surface}; border-left:1px solid {border}; }
            QScrollArea#detailsPanel > QWidget > QWidget { background:{surface}; }
            QWidget#settingsHeader { background:{surface}; border-bottom:1px solid {border_subtle}; }
            QLabel#settingsTitle { font-weight:700; font-size:15px; color:{text_primary}; }
            QToolButton#settingsClose { border:none; background:transparent; color:{text_muted}; font-size:14px; padding:4px 8px; border-radius:6px; }
            QToolButton#settingsClose:hover { background:{hover}; color:{text_primary}; }
            QListWidget#settingsNav { background:{surface_muted}; border-right:1px solid {border_subtle}; padding:8px 4px; }
            QListWidget#settingsNav::item { padding:9px 12px; border-radius:8px; margin:1px 4px; color:{text_secondary}; }
            QListWidget#settingsNav::item:selected { background:{selection_tint}; color:{text_primary}; font-weight:600; }
            QListWidget#settingsNav::item:hover { background:{hover}; }
            QStackedWidget#settingsPages { background:{surface}; }
            QLabel#pageHeading { font-size:18px; font-weight:600; color:{text_primary}; }
            QLabel#pageSubtitle { font-size:12px; color:{text_muted}; padding-bottom:4px; }
            QLabel#fieldLabel { font-size:11px; font-weight:600; color:{text_muted}; text-transform:uppercase; letter-spacing:0.5px; }
            QLabel#profileIdentity { font-size:13px; color:{text_primary}; }
            QGroupBox#detailsGroup { border:1px solid {border}; border-radius:10px; margin-top:8px; padding-top:8px; background:{surface}; color:{text_primary}; }
            QGroupBox#detailsGroup::title { subcontrol-origin:margin; left:12px; padding:0 4px; color:{primary}; font-weight:600; }
            QLineEdit, QSpinBox, QPlainTextEdit { background:{surface}; color:{text_primary}; border:1px solid {border_input}; border-radius:8px; padding:6px 9px; selection-background-color:{primary}; selection-color:#ffffff; }
            QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border:1px solid {primary}; }
            QPushButton { background:{surface}; border:1px solid {border_input}; border-radius:8px; padding:6px 14px; color:{text_primary}; }
            QPushButton:hover { background:{hover}; }
            QPushButton:disabled { color:{text_disabled}; background:{secondary_header_tint}; border:1px solid {border}; }
            QPushButton#primary { background:{primary}; color:#ffffff; border:1px solid {primary}; font-weight:600; }
            QPushButton#primary:hover { background:{primary_hover}; border:1px solid {primary_hover}; }
            QPushButton#primary:disabled { background:{primary_disabled}; color:#ffffff; border:1px solid {primary_disabled}; }
            QPushButton#ghost { background:transparent; border:none; color:{primary}; padding:4px 8px; }
            QPushButton#ghost:hover { background:{primary_ghost_hover}; }
            QCheckBox { spacing:6px; color:{text_primary}; }
            QStatusBar { background:{surface}; border-top:1px solid {border}; color:{text_muted}; }
            QProgressBar { border:1px solid {border_input}; border-radius:6px; background:{surface}; color:{text_primary}; height:14px; text-align:center; }
            QProgressBar::chunk { background:{primary}; border-radius:6px; }
        )");
        // Substitute the {name} placeholders with active-theme values. Done
        // as a pass over named keys so the QSS source stays human-readable
        // rather than a chain of ~30 .arg() calls.
        const std::pair<const char*, const char*> subs[] = {
            {"app_background",        t.app_background},
            {"surface",               t.surface},
            {"surface_muted",         t.surface_muted},
            {"chat_area",             t.chat_area},
            {"border",                t.border},
            {"border_subtle",         t.border_subtle},
            {"border_input",          t.border_input},
            {"splitter",              t.splitter},
            {"selection_tint",        t.selection_tint},
            {"hover",                 t.hover},
            {"primary",               t.primary},
            {"primary_hover",         t.primary_hover},
            {"primary_disabled",      t.primary_disabled},
            {"primary_ghost_hover",   t.primary_ghost_hover},
            {"secondary_header_tint", t.secondary_header_tint},
            {"in_chat_search_bg",     t.in_chat_search_bg},
            {"text_primary",          t.text_primary},
            {"text_secondary",        t.text_secondary},
            {"text_muted",            t.text_muted},
            {"text_disabled",         t.text_disabled},
        };
        for (const auto& [name, value] : subs) {
            css.replace(QString::fromUtf8("{") + QString::fromUtf8(name) + QString::fromUtf8("}"),
                        QString::fromUtf8(value));
        }
        // font_stack + font_px aren't theme-dependent but stay in the same
        // substitution scheme so the QSS template doesn't mix two styles.
        css.replace(QStringLiteral("{font_stack}"), QString::fromUtf8(dt::kFontStack));
        css.replace(QStringLiteral("{font_px}"),    QString::number(dt::kFontPxBase));
        return css;
    }

    void request_thumbnails_for_visible_messages() {
        // M148: scan the selected conversation for image-MIME attachments
        // that aren't in the cache + aren't already being fetched, then
        // kick a worker thread per miss. Cache is capped at 64 entries
        // (newest wins) so a long history of images doesn't bloat memory.
        if (client_ == nullptr) return;
        const auto* conv = store_.selected_conversation();
        if (conv == nullptr) return;
        for (auto it = conv->messages.rbegin(); it != conv->messages.rend(); ++it) {
            const auto& m = *it;
            if (m.attachment_id.empty()) continue;
            const QString key = qstr(m.attachment_id);
            if (m.mime_type.rfind("image/", 0) != 0) continue;
            if (thumbnail_cache_.contains(key)) continue;
            if (thumbnail_inflight_.contains(key)) continue;
            thumbnail_inflight_.insert(key);
            const std::string aid = m.attachment_id;
            auto client = client_;
            std::thread([this, client, aid, key] {
                const auto fetched = client->fetch_attachment(aid);
                QMetaObject::invokeMethod(this, [this, key, fetched] {
                    if (shutting_down_) return;
                    thumbnail_inflight_.remove(key);
                    if (!fetched.ok || fetched.content.empty()) return;
                    QImage img;
                    img.loadFromData(QByteArray::fromStdString(fetched.content));
                    if (img.isNull()) return;
                    if (img.width() > 480 || img.height() > 480) {
                        img = img.scaled(480, 480, Qt::KeepAspectRatio,
                                          Qt::SmoothTransformation);
                    }
                    if (thumbnail_cache_.size() >= 64) {
                        // Drop an arbitrary entry to keep memory bounded.
                        thumbnail_cache_.erase(thumbnail_cache_.begin());
                    }
                    thumbnail_cache_.insert(key, QPixmap::fromImage(img));
                    if (messages_ != nullptr) {
                        messages_->setThumbnailCache(thumbnail_cache_);
                    }
                }, Qt::QueuedConnection);
            }).detach();
            // Cap to ~8 inflight at a time so fast scrolls don't flood.
            if (thumbnail_inflight_.size() >= 8) break;
        }
    }

    void handle_typing_pulse_push(const std::string& envelope) {
        // M147: parse the JSON envelope sent by the server (shape:
        // {type:"typing_pulse", payload:{conversation_id, is_typing,
        // sender_user_id}, ...}) and flip the indicator. Self-pulses are
        // suppressed — server filters by `_fanout_to_conversation`'s
        // origin_session_id but a defensive check costs nothing here.
        if (typing_indicator_ == nullptr) return;
        const QJsonDocument doc = QJsonDocument::fromJson(
            QByteArray::fromStdString(envelope));
        if (!doc.isObject()) return;
        const QJsonObject root = doc.object();
        const QJsonObject payload = root.value("payload").toObject();
        const QString sender = payload.value("sender_user_id").toString();
        const QString conv = payload.value("conversation_id").toString();
        const bool is_typing = payload.value("is_typing").toBool(true);
        if (sender.isEmpty() || sender == qstr(store_.current_user_id())) return;
        // Only show typing for the currently-open conversation; pulses
        // from other rooms would be confusing in the header subtitle.
        if (conv != qstr(store_.selected_conversation_id())) return;
        if (is_typing) {
            typing_indicator_->setActive(sender, true);
            if (typing_decay_timer_ != nullptr) typing_decay_timer_->start();
        } else {
            typing_indicator_->setActive(QString(), false);
            if (typing_decay_timer_ != nullptr) typing_decay_timer_->stop();
        }
    }

    void show_chat_info_dialog() {
        // M145: Telegram-style chat-info popup. Shows
        //   title + conv id (header)
        //   participants list (each entry "uid · role" — owner/admin/member
        //                      derived from M103 participant_role_for if
        //                      available; falls back to plain id)
        //   pinned messages list ("[id] sender · snippet")
        //   summary footer (attachment count + last sync version)
        // Built on every click so the lists stay current; closes on Esc / X.
        const auto* conv = store_.selected_conversation();
        if (conv == nullptr) {
            QMessageBox::information(this, "Chat info",
                "Pick a chat from the list first.");
            return;
        }
        auto* dlg = new QDialog(this);
        dlg->setWindowTitle("Chat info");
        dlg->setAttribute(Qt::WA_DeleteOnClose);
        // M150: dock as a frameless tool window on the right edge of the
        // main window and slide in from off-screen-right via
        // QPropertyAnimation. Closing animates it back out before
        // accepting so the disappearance feels intentional rather than
        // a hard pop.
        dlg->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint);
        dlg->setAttribute(Qt::WA_TranslucentBackground, false);
        const int panelW = 360;
        const QRect mainGeo = this->geometry();
        const int targetY = mainGeo.top() + 32;  // skip past system title
        const int targetH = std::max(360, mainGeo.height() - 64);
        const int targetX = mainGeo.right() - panelW - 8;
        const QRect dockedGeo(targetX, targetY, panelW, targetH);
        const QRect offGeo(mainGeo.right() + 8, targetY, panelW, targetH);
        dlg->setGeometry(offGeo);

        auto* root = new QVBoxLayout(dlg);
        root->setSpacing(10);
        root->setContentsMargins(16, 14, 16, 14);

        const QString title = conv->title.empty()
            ? qstr(conv->conversation_id)
            : qstr(conv->title);
        auto* title_label = new QLabel(QString("<b style='font-size:14pt'>%1</b>")
            .arg(title.toHtmlEscaped()));
        title_label->setTextFormat(Qt::RichText);
        root->addWidget(title_label);
        auto* sub_label = new QLabel(QString("<span style='color:#7c8a96'>%1 · %2 participants</span>")
            .arg(qstr(conv->conversation_id).toHtmlEscaped())
            .arg(conv->participant_user_ids.size()));
        sub_label->setTextFormat(Qt::RichText);
        root->addWidget(sub_label);

        // Participants
        auto* members_label = new QLabel("<b>Members</b>");
        members_label->setTextFormat(Qt::RichText);
        root->addWidget(members_label);
        auto* members = new QListWidget();
        members->setFrameShape(QFrame::NoFrame);
        for (const auto& uid : conv->participant_user_ids) {
            members->addItem(qstr(uid));
        }
        if (conv->participant_user_ids.empty()) {
            members->addItem("(no participant data — try Connect to refresh)");
        }
        root->addWidget(members, 1);

        // Pinned + attachments summary
        std::size_t attachment_count = 0;
        std::vector<const telegram_like::client::app_desktop::DesktopMessage*> pinned_list;
        for (const auto& m : conv->messages) {
            if (!m.attachment_id.empty()) ++attachment_count;
            if (m.pinned && !m.deleted) pinned_list.push_back(&m);
        }
        auto* pinned_label = new QLabel(
            QString("<b>Pinned (%1)</b>").arg(pinned_list.size()));
        pinned_label->setTextFormat(Qt::RichText);
        root->addWidget(pinned_label);
        auto* pinned_widget = new QListWidget();
        pinned_widget->setFrameShape(QFrame::NoFrame);
        pinned_widget->setMaximumHeight(96);
        for (const auto* m : pinned_list) {
            pinned_widget->addItem(QString("[%1] %2  %3")
                .arg(qstr(m->message_id),
                     qstr(m->sender_user_id),
                     qstr(m->text).left(48)));
        }
        if (pinned_list.empty()) pinned_widget->addItem("(nothing pinned)");
        root->addWidget(pinned_widget);

        auto* footer = new QLabel(QString("Attachments: %1   Sync version: %2")
            .arg(attachment_count)
            .arg(conv->sync_version));
        footer->setStyleSheet("color:#7c8a96; font-size:11px;");
        root->addWidget(footer);

        auto* btn_row = new QHBoxLayout();
        btn_row->addStretch(1);
        auto* close_btn = new QPushButton("Close");
        close_btn->setObjectName("primary");
        // M150: closing animates the panel back off-screen-right before
        // the dialog actually accepts, so the disappearance feels like
        // a slide rather than a pop.
        QObject::connect(close_btn, &QPushButton::clicked, dlg, [dlg, dockedGeo, offGeo] {
            auto* outAnim = new QPropertyAnimation(dlg, "geometry", dlg);
            outAnim->setDuration(180);
            outAnim->setEasingCurve(QEasingCurve::InCubic);
            outAnim->setStartValue(dockedGeo);
            outAnim->setEndValue(offGeo);
            QObject::connect(outAnim, &QPropertyAnimation::finished, dlg, &QDialog::accept);
            outAnim->start(QAbstractAnimation::DeleteWhenStopped);
        });
        btn_row->addWidget(close_btn);
        root->addLayout(btn_row);

        dlg->show();
        // M150: slide-in animation from off-screen right to the docked
        // position. 220 ms with an out-cubic curve for a Telegram-feel
        // swoosh. DeleteWhenStopped frees the QPropertyAnimation once
        // the slide finishes.
        auto* inAnim = new QPropertyAnimation(dlg, "geometry", dlg);
        inAnim->setDuration(220);
        inAnim->setEasingCurve(QEasingCurve::OutCubic);
        inAnim->setStartValue(offGeo);
        inAnim->setEndValue(dockedGeo);
        inAnim->start(QAbstractAnimation::DeleteWhenStopped);
    }

    void update_chat_header() {
        const auto* conversation = store_.selected_conversation();
        if (conversation == nullptr) {
            chat_header_title_->setText("No chat selected");
            chat_header_subtitle_->setText("Pick a chat from the list");
            return;
        }
        const QString title = conversation->title.empty()
            ? qstr(conversation->conversation_id)
            : qstr(conversation->title);
        chat_header_title_->setText(title);
        std::string subtitle = conversation->conversation_id;
        if (!conversation->participant_user_ids.empty()) {
            subtitle += "  ·  ";
            for (std::size_t i = 0; i < conversation->participant_user_ids.size(); ++i) {
                if (i > 0) subtitle += ", ";
                subtitle += conversation->participant_user_ids[i];
            }
        }
        chat_header_subtitle_->setText(qstr(subtitle));
    }

    void toggle_details_panel() {
        const bool visible = details_panel_->isVisible();
        details_panel_->setVisible(!visible);
        toggle_details_->setText(visible ? "Settings ▸" : "Settings ▾");
    }

    static QColor avatar_color_for(const std::string& seed) {
        // 8 Telegram-style accent colors, picked deterministically from seed.
        static const QColor palette[] = {
            QColor("#e17076"), QColor("#7bc862"), QColor("#65aadd"),
            QColor("#a695e7"), QColor("#ee7aae"), QColor("#6ec9cb"),
            QColor("#faa774"), QColor("#7d8ea0")
        };
        if (seed.empty()) return palette[0];
        unsigned hash = 0;
        for (char c : seed) hash = hash * 31u + static_cast<unsigned char>(c);
        return palette[hash % (sizeof(palette) / sizeof(palette[0]))];
    }

    void update_avatar_pixmap(const std::string& user_id, const std::string& display_name) {
        if (avatar_label_ == nullptr) return;
        const std::string& source = display_name.empty() ? user_id : display_name;
        QString initials;
        if (!source.empty()) {
            const auto qsource = qstr(source).trimmed();
            if (!qsource.isEmpty()) {
                initials += qsource.at(0).toUpper();
                const int space = qsource.indexOf(' ');
                if (space >= 0 && space + 1 < qsource.size()) {
                    initials += qsource.at(space + 1).toUpper();
                }
            }
        }
        if (initials.isEmpty()) initials = "?";

        const int side = 96;
        QPixmap pixmap(side, side);
        pixmap.fill(Qt::transparent);
        QPainter painter(&pixmap);
        painter.setRenderHint(QPainter::Antialiasing);
        const QColor bg = avatar_color_for(source);
        painter.setBrush(bg);
        painter.setPen(Qt::NoPen);
        painter.drawEllipse(0, 0, side, side);
        QFont f = painter.font();
        f.setBold(true);
        f.setPointSize(28);
        painter.setFont(f);
        painter.setPen(Qt::white);
        painter.drawText(QRect(0, 0, side, side), Qt::AlignCenter, initials);
        avatar_label_->setPixmap(pixmap);
    }

    void update_profile_identity(const std::string& user_id, const std::string& display_name) {
        if (profile_identity_label_ == nullptr) return;
        if (user_id.empty()) {
            profile_identity_label_->setText("Not connected");
            return;
        }
        const auto display = display_name.empty() ? user_id : display_name;
        const QString html = QStringLiteral(
            "<div style='font-size:16px;font-weight:600;color:#0f1419;'>%1</div>"
            "<div style='font-size:12px;color:#7c8a96;'>%2</div>")
            .arg(qstr(display).toHtmlEscaped(),
                 qstr(user_id).toHtmlEscaped());
        profile_identity_label_->setText(html);
    }

    void render_store() {
        const auto focused_id = focused_search_message_id();
        // M138: drive the BubbleListView from the store + theme palette.
        // The previous setHtml(render_selected_timeline_html(...)) path is
        // kept on DesktopChatStore for store_test (which still verifies the
        // HTML renderer) but app_desktop no longer points its main view at
        // it — the bubble delegate paints directly.
        namespace dt = telegram_like::client::app_desktop::design;
        const auto& t = dt::active_theme();
        telegram_like::client::app_desktop::DesktopBubblePalette palette;
        palette.chat_area_bg     = t.chat_area;
        palette.own_bubble       = t.own_bubble_bottom;
        palette.own_bubble_text  = t.own_bubble_text;
        palette.peer_bubble      = t.peer_bubble;
        palette.peer_bubble_text = t.peer_bubble_text;
        palette.primary          = t.primary;
        palette.text_muted       = t.text_muted;
        palette.tick_sent        = t.tick_unread;
        palette.tick_read        = t.tick_read;
        // failed_bubble stays at the default `#ffd7cf` — it's a neutral
        // alarm signal independent of theme so the red shows in both modes.
        messages_->setBubblePalette(palette);
        messages_->setStore(&store_, store_.current_user_id());
        messages_->setSearchHighlight(message_search_->text().trimmed(), qstr(focused_id));
        messages_->setThumbnailCache(thumbnail_cache_);
        messages_->refresh();
        request_thumbnails_for_visible_messages();
        // M140: theme the typing indicator from the same palette so the
        // dots flip to the dark dot color when the user toggles theme.
        if (typing_indicator_ != nullptr) {
            typing_indicator_->setDotColor(QColor(t.text_muted));
            typing_indicator_->setLabelColor(QColor(t.text_muted));
        }
        // M144: refresh the pin bar — show the first (oldest) pinned
        // message in the conversation, hide the bar when nothing is pinned.
        if (pin_bar_ != nullptr) {
            const auto* conv = store_.selected_conversation();
            const telegram_like::client::app_desktop::DesktopMessage* pinned = nullptr;
            if (conv != nullptr) {
                for (const auto& m : conv->messages) {
                    if (m.pinned && !m.deleted) { pinned = &m; break; }
                }
            }
            if (pinned == nullptr) {
                pin_bar_->setVisible(false);
                pin_bar_target_id_.clear();
            } else {
                pin_bar_target_id_ = qstr(pinned->message_id);
                const QString sender = qstr(pinned->sender_user_id);
                const QString snippet = qstr(pinned->text).left(80);
                pin_bar_->setText(QString::fromUtf8(
                    "\xf0\x9f\x93\x8c  <b>Pinned by %1</b>  %2")
                    .arg(sender, snippet));
                pin_bar_->setStyleSheet(QString::fromUtf8(
                    "QPushButton#pinBar { text-align:left; padding:6px 12px; "
                    "border:none; border-bottom:1px solid %1; "
                    "background:%2; color:%3; } "
                    "QPushButton#pinBar:hover { background:%4; }")
                    .arg(QString::fromUtf8(t.border_subtle),
                         QString::fromUtf8(t.surface_muted),
                         QString::fromUtf8(t.text_primary),
                         QString::fromUtf8(t.hover)));
                pin_bar_->setVisible(true);
            }
        }
        render_conversation_list();
        render_search_status();
        update_chat_header();
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
        const auto use_tls = tls_->isChecked();
        const auto tls_insecure = tls_insecure_->isChecked();
        const auto tls_server_name = args_.tls_server_name;
        const auto user = str(user_->text());
        const auto password = str(password_->text());
        const auto display_name = str(display_name_->text());
        const auto device = str(device_->text());
        const auto selected_conversation = str(conversation_->text());

        store_.set_selected_conversation(selected_conversation);
        load_cache();
        render_store();
        const auto cursors = store_.sync_cursors();

        std::thread([this, host, port, use_tls, tls_insecure, tls_server_name,
                     user, password, display_name, device, cursors, create_account] {
            auto next_client = std::make_shared<ControlPlaneClient>();
            const bool connected = use_tls
                ? next_client->connect_tls(host, port, tls_insecure, tls_server_name)
                : next_client->connect(host, port);
            if (!connected) {
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
                    // M147: typing pulses are UI-only; they don't go through
                    // the chat store at all. Parse the envelope, flip the
                    // indicator with the (re)started 5s decay, return.
                    if (type == "typing_pulse") {
                        handle_typing_pulse_push(envelope);
                        return;
                    }
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
                set_remote_action_enabled(true);
                set_call_action_enabled(true);
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

    void edit_message_action() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        bool ok = false;
        const QString new_text = QInputDialog::getText(
            this, "Edit message",
            "New text for " + qstr(message_id) + ":",
            QLineEdit::Normal, QString(), &ok);
        if (!ok || new_text.trimmed().isEmpty()) return;
        const auto text = str(new_text);
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id, text] {
            const auto result = client->edit_message(conversation, message_id, text);
            QMetaObject::invokeMethod(this, [this, conversation, message_id, text, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] edit failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                // Server fans MESSAGE_EDITED to others; actor must apply locally.
                store_.apply_message_edited(conversation, message_id, text);
                save_cache();
                render_store();
                statusBar()->showMessage("Edited " + qstr(message_id));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void delete_message_action() {
        if (!client_ || message_action_id_->text().trimmed().isEmpty()) return;
        const auto conversation = str(conversation_->text());
        const auto message_id = str(message_action_id_->text().trimmed());
        const auto answer = QMessageBox::question(
            this, "Delete message",
            "Delete " + qstr(message_id) + "? This cannot be undone.",
            QMessageBox::Yes | QMessageBox::No, QMessageBox::No);
        if (answer != QMessageBox::Yes) return;
        set_message_action_enabled(false);
        auto client = client_;
        std::thread([this, client, conversation, message_id] {
            const auto result = client->delete_message(conversation, message_id);
            QMetaObject::invokeMethod(this, [this, conversation, message_id, result] {
                if (shutting_down_) return;
                set_message_action_enabled(true);
                if (!result.ok) {
                    append_line("[error] delete failed: " + qstr(result.error_code + " " + result.error_message));
                    return;
                }
                store_.apply_message_deleted(conversation, message_id);
                save_cache();
                render_store();
                statusBar()->showMessage("Deleted " + qstr(message_id));
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
        // M126: prefer chunked upload for files > 1 MB so we get byte-level
        // progress updates. Smaller files keep the single-shot path because
        // the per-chunk RPC overhead dominates for tiny payloads.
        constexpr std::size_t kChunkedThreshold = 1u * 1024 * 1024;
        const bool use_chunked = content.size() > kChunkedThreshold;
        std::thread([this, client, conversation, caption, filename, mime_type, content, local_message_id, use_chunked] {
            telegram_like::client::transport::MessageResult sent;
            if (use_chunked) {
                auto progress = [this, total = content.size()](std::size_t bytes_uploaded, std::size_t bytes_total) {
                    const int pct = bytes_total == 0 ? 0
                        : static_cast<int>((bytes_uploaded * 100) / bytes_total);
                    QMetaObject::invokeMethod(this, [this, bytes_uploaded, bytes_total, pct] {
                        if (shutting_down_) return;
                        set_transfer_progress(
                            "Uploading "
                            + std::to_string(bytes_uploaded) + " / " + std::to_string(bytes_total)
                            + " B",
                            pct);
                    }, Qt::QueuedConnection);
                };
                sent = client->send_attachment_chunked(
                    conversation, caption, filename, mime_type, content, progress);
            } else {
                sent = client->send_attachment(
                    conversation, caption, filename, mime_type, content);
            }
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
                // M125: real thumbnail preview for image attachments. Decode
                // the bytes into a QPixmap and pop a non-modal dialog so the
                // user immediately sees the image they just downloaded.
                if (fetched.mime_type.rfind("image/", 0) == 0) {
                    QPixmap pixmap;
                    const QByteArray image_bytes(fetched.content.data(), static_cast<int>(fetched.content.size()));
                    if (pixmap.loadFromData(image_bytes)) {
                        auto* preview = new QDialog(this);
                        preview->setAttribute(Qt::WA_DeleteOnClose);
                        preview->setWindowTitle(qstr("Preview — " + fetched.filename));
                        auto* layout = new QVBoxLayout(preview);
                        auto* label = new QLabel();
                        label->setPixmap(pixmap.scaled(560, 560, Qt::KeepAspectRatio, Qt::SmoothTransformation));
                        label->setAlignment(Qt::AlignCenter);
                        layout->addWidget(label);
                        auto* meta = new QLabel(qstr(fetched.filename + "  ·  "
                            + std::to_string(fetched.size_bytes) + " B  ·  " + fetched.mime_type));
                        meta->setObjectName("pageSubtitle");
                        layout->addWidget(meta);
                        preview->resize(600, 640);
                        preview->show();
                    }
                }
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

    enum class RemoteOp { Approve, Reject, Cancel, Terminate };
    enum class CallOp { Accept, Decline, End };

    void append_call_log(const QString& line) {
        if (!call_log_) return;
        call_log_->appendPlainText(line);
    }

    void call_invite_action() {
        if (!client_) return;
        const auto callee_user = str(call_callee_user_->text().trimmed());
        const auto callee_device = str(call_callee_device_->text().trimmed());
        if (callee_user.empty() || callee_device.empty()) {
            append_call_log("[error] callee user_id + device_id required");
            return;
        }
        const auto kind = str(call_kind_->currentText());
        set_call_action_enabled(false);
        auto client = client_;
        std::thread([this, client, callee_user, callee_device, kind] {
            const auto r = client->call_invite(callee_user, callee_device, kind);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_call_action_enabled(true);
                if (!r.ok) {
                    append_call_log(qstr("[invite error] " + r.error_code + " " + r.error_message));
                    return;
                }
                if (call_id_input_) call_id_input_->setText(qstr(r.call_id));
                append_call_log(qstr("[invite ok] call_id=" + r.call_id + " state=" + r.state));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void call_terminal_action(CallOp op) {
        if (!client_) return;
        const auto cid = str(call_id_input_->text().trimmed());
        if (cid.empty()) { append_call_log("[error] call_id required"); return; }
        set_call_action_enabled(false);
        auto client = client_;
        std::thread([this, client, cid, op] {
            telegram_like::client::transport::CallStateResult r;
            std::string verb;
            switch (op) {
                case CallOp::Accept:  verb = "accept";  r = client->call_accept(cid);  break;
                case CallOp::Decline: verb = "decline"; r = client->call_decline(cid); break;
                case CallOp::End:     verb = "end";     r = client->call_end(cid);     break;
            }
            QMetaObject::invokeMethod(this, [this, verb, r] {
                if (shutting_down_) return;
                set_call_action_enabled(true);
                if (!r.ok) {
                    append_call_log(qstr("[" + verb + " error] " + r.error_code + " " + r.error_message));
                    return;
                }
                append_call_log(qstr("[" + verb + " ok] state=" + r.state
                                     + (r.detail.empty() ? std::string() : " " + r.detail)));
            }, Qt::QueuedConnection);
        }).detach();
    }


    void append_remote_log(const QString& line) {
        if (!remote_log_) return;
        remote_log_->appendPlainText(line);
    }

    void remote_invite_action() {
        if (!client_) return;
        const auto target_device = str(remote_target_device_->text().trimmed());
        if (target_device.empty()) {
            append_remote_log("[error] target device_id is required");
            return;
        }
        const auto requester_device = str(device_->text().trimmed());
        if (requester_device.empty()) {
            append_remote_log("[error] requester device_id (Connection > Device) is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, requester_device, target_device] {
            const auto result = client->remote_invite(requester_device, target_device);
            QMetaObject::invokeMethod(this, [this, result] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!result.ok) {
                    append_remote_log(qstr(
                        "[invite error] " + result.error_code + " " + result.error_message));
                    return;
                }
                if (remote_session_id_input_) {
                    remote_session_id_input_->setText(qstr(result.remote_session_id));
                }
                append_remote_log(qstr(
                    "[invite ok] remote_session_id=" + result.remote_session_id
                    + " state=" + result.state));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void remote_terminal_action(RemoteOp op) {
        if (!client_) return;
        const auto rs_id = str(remote_session_id_input_->text().trimmed());
        if (rs_id.empty()) {
            append_remote_log("[error] remote_session_id is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, rs_id, op] {
            std::string verb;
            std::string state;
            std::string detail;
            std::string error_code;
            std::string error_message;
            bool ok = false;
            switch (op) {
                case RemoteOp::Approve: {
                    verb = "approve";
                    auto r = client->remote_approve(rs_id);
                    ok = r.ok;
                    state = r.state;
                    error_code = r.error_code;
                    error_message = r.error_message;
                    if (ok) {
                        detail = "relay=" + r.relay_endpoint + " region=" + r.relay_region;
                    }
                    break;
                }
                case RemoteOp::Reject: {
                    verb = "reject";
                    auto r = client->remote_reject(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
                case RemoteOp::Cancel: {
                    verb = "cancel";
                    auto r = client->remote_cancel(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
                case RemoteOp::Terminate: {
                    verb = "terminate";
                    auto r = client->remote_terminate(rs_id);
                    ok = r.ok; state = r.state; detail = r.detail;
                    error_code = r.error_code; error_message = r.error_message;
                    break;
                }
            }
            QMetaObject::invokeMethod(this, [this, verb, ok, state, detail, error_code, error_message] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!ok) {
                    append_remote_log(qstr("[" + verb + " error] " + error_code + " " + error_message));
                    return;
                }
                append_remote_log(qstr("[" + verb + " ok] state=" + state
                                       + (detail.empty() ? std::string() : " " + detail)));
            }, Qt::QueuedConnection);
        }).detach();
    }

    void remote_rendezvous_action() {
        if (!client_) return;
        const auto rs_id = str(remote_session_id_input_->text().trimmed());
        if (rs_id.empty()) {
            append_remote_log("[error] remote_session_id is required");
            return;
        }
        set_remote_action_enabled(false);
        auto client = client_;
        std::thread([this, client, rs_id] {
            const auto r = client->remote_rendezvous_request(rs_id);
            QMetaObject::invokeMethod(this, [this, r] {
                if (shutting_down_) return;
                set_remote_action_enabled(true);
                if (!r.ok) {
                    append_remote_log(qstr(
                        "[rendezvous error] " + r.error_code + " " + r.error_message));
                    return;
                }
                std::string summary = "[rendezvous ok] state=" + r.state
                    + " region=" + r.relay_region
                    + " relay=" + r.relay_endpoint
                    + " key=" + (r.relay_key_b64.empty() ? "(none)" : "(set)")
                    + " candidates=" + std::to_string(r.candidates.size());
                append_remote_log(qstr(summary));
                for (const auto& c : r.candidates) {
                    append_remote_log(qstr(
                        "  " + c.kind + " " + c.address + ":" + std::to_string(c.port)
                        + " prio=" + std::to_string(c.priority)));
                }
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
        update_avatar_pixmap(result.user_id, result.display_name);
        update_profile_identity(result.user_id, result.display_name);
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

    void set_remote_action_enabled(bool enabled) {
        if (remote_invite_) remote_invite_->setEnabled(enabled);
        if (remote_approve_) remote_approve_->setEnabled(enabled);
        if (remote_reject_) remote_reject_->setEnabled(enabled);
        if (remote_cancel_) remote_cancel_->setEnabled(enabled);
        if (remote_terminate_) remote_terminate_->setEnabled(enabled);
        if (remote_rendezvous_) remote_rendezvous_->setEnabled(enabled);
    }

    void set_call_action_enabled(bool enabled) {
        if (call_invite_) call_invite_->setEnabled(enabled);
        if (call_accept_) call_accept_->setEnabled(enabled);
        if (call_decline_) call_decline_->setEnabled(enabled);
        if (call_end_) call_end_->setEnabled(enabled);
    }

    void set_message_action_enabled(bool enabled) {
        if (reply_) reply_->setEnabled(enabled);
        if (forward_) forward_->setEnabled(enabled);
        if (react_) react_->setEnabled(enabled);
        if (pin_) pin_->setEnabled(enabled);
        if (unpin_) unpin_->setEnabled(enabled);
        if (edit_) edit_->setEnabled(enabled);
        if (delete_) delete_->setEnabled(enabled);
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
    QCheckBox* tls_ {nullptr};
    QCheckBox* tls_insecure_ {nullptr};
    QLineEdit* conversation_ {nullptr};
    QLineEdit* user_ {nullptr};
    QLineEdit* password_ {nullptr};
    QLineEdit* display_name_ {nullptr};
    QLineEdit* device_ {nullptr};
    QPushButton* connect_ {nullptr};
    QPushButton* register_ {nullptr};
    // M139: Appearance page light/dark radios. Toggling either re-applies
    // the QApplication stylesheet + bubble palette and persists the
    // choice in QSettings.
    QRadioButton* appearance_light_ {nullptr};
    QRadioButton* appearance_dark_ {nullptr};
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
    telegram_like::client::app_desktop::BubbleListView* messages_ {nullptr};
    telegram_like::client::app_desktop::TypingIndicator* typing_indicator_ {nullptr};
    // M144: top strip showing the most-recently pinned message snippet;
    // click jumps to the message in the bubble view.
    QPushButton* pin_bar_ {nullptr};
    QString pin_bar_target_id_;
    // M145: chat info dialog trigger; the dialog itself is constructed
    // on-demand so the QListWidget contents stay in sync with the latest
    // store snapshot.
    QToolButton* chat_info_btn_ {nullptr};
    // M147: client-side TYPING_PULSE state. last_typing_sent_ms_ debounces
    // outgoing pulses to ~one every 2s while the composer is non-empty;
    // typing_decay_timer_ clears the local indicator 5s after the most
    // recent inbound pulse so a missed STOP doesn't leave the dots
    // spinning forever.
    qint64 last_typing_sent_ms_ {0};
    QTimer* typing_decay_timer_ {nullptr};
    // M148: image thumbnail cache keyed by attachment_id. Populated lazily
    // by request_thumbnails_for_visible_messages — render_store iterates
    // image attachments and kicks a worker per cache miss; on success the
    // bytes get decoded into a QPixmap and BubbleListView::setThumbnailCache
    // refreshes. Sized cap is enforced at decode time (240×240).
    QHash<QString, QPixmap> thumbnail_cache_;
    QSet<QString> thumbnail_inflight_;
    QLineEdit* composer_ {nullptr};
    QPushButton* attach_ {nullptr};
    QLineEdit* message_action_id_ {nullptr};
    QLineEdit* reaction_emoji_ {nullptr};
    QPushButton* reply_ {nullptr};
    QPushButton* forward_ {nullptr};
    QPushButton* react_ {nullptr};
    QPushButton* pin_ {nullptr};
    QPushButton* unpin_ {nullptr};
    QPushButton* edit_ {nullptr};
    QPushButton* delete_ {nullptr};
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
    QLabel* chat_header_title_ {nullptr};
    QLabel* chat_header_subtitle_ {nullptr};
    QScrollArea* details_panel_ {nullptr};
    QPushButton* toggle_details_ {nullptr};
    QListWidget* settings_nav_ {nullptr};
    QStackedWidget* settings_pages_ {nullptr};
    QLabel* avatar_label_ {nullptr};
    QLabel* profile_identity_label_ {nullptr};
    // M108: remote-control widgets
    QLineEdit* remote_target_device_ {nullptr};
    QPushButton* remote_invite_ {nullptr};
    QLineEdit* remote_session_id_input_ {nullptr};
    QPushButton* remote_approve_ {nullptr};
    QPushButton* remote_reject_ {nullptr};
    QPushButton* remote_cancel_ {nullptr};
    QPushButton* remote_terminate_ {nullptr};
    QPushButton* remote_rendezvous_ {nullptr};
    QPlainTextEdit* remote_log_ {nullptr};
    // M128: voice/video call widgets
    QLineEdit* call_callee_user_ {nullptr};
    QLineEdit* call_callee_device_ {nullptr};
    QComboBox* call_kind_ {nullptr};
    QLineEdit* call_id_input_ {nullptr};
    QPushButton* call_invite_ {nullptr};
    QPushButton* call_accept_ {nullptr};
    QPushButton* call_decline_ {nullptr};
    QPushButton* call_end_ {nullptr};
    QPlainTextEdit* call_log_ {nullptr};
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
    QApplication::setOrganizationName(QStringLiteral("Telegram-like"));
    QApplication::setApplicationName(QStringLiteral("app_desktop"));
    // M139: load the persisted Appearance choice BEFORE the window
    // constructor so the first stylesheet pass picks up the saved theme
    // (env var still wins for the very first run when the setting is
    // absent — see active_theme()'s lazy init).
    {
        QSettings prefs;
        if (prefs.contains(QStringLiteral("appearance/dark_theme"))) {
            telegram_like::client::app_desktop::design::set_active_theme(
                prefs.value(QStringLiteral("appearance/dark_theme")).toBool());
        }
    }
    DesktopWindow window(args);
    window.show();
    return app.exec();
}
