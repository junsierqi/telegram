#include "app/app_shell.h"

#include "app/client_session.h"
#include "app/client_state.h"
#include "remote_control/remote_session_controller.h"
#include "transport/udp_media_probe.h"
#include "transport/udp_frame_stream.h"

#include <cstdlib>
#include "transport/session_gateway_client.h"
#include "shared/protocol/control_envelope.h"
#include "shared/protocol/message_types.h"
#include "shared/protocol/remote_session.h"

#include <iostream>
#include <optional>
#include <variant>

namespace telegram_like::client::app {

namespace {

std::optional<ClientSession> login_user(transport::SessionGatewayClient& gateway,
                                        const std::string& username,
                                        const std::string& password,
                                        const std::string& device_id,
                                        const std::string& correlation_id) {
    const auto login_request = gateway.compose_request_json(
        transport::LoginRequestMessage {
            .username = username,
            .password = password,
            .device_id = device_id,
            .correlation_id = correlation_id,
        });
    std::cout << "[client] outbound " << login_request << '\n';

    const auto login_response = gateway.send_request_json(login_request);
    if (!login_response.has_value()) {
        return std::nullopt;
    }

    const auto login_message = gateway.parse_response_message(*login_response);
    if (!login_message.has_value()) {
        return std::nullopt;
    }
    std::cout << "[client] inbound " << login_message->raw_json << '\n';

    const auto* payload =
        std::get_if<transport::LoginResponsePayload>(&login_message->payload);
    if (payload == nullptr) {
        return std::nullopt;
    }

    return ClientSession {
        .username = username,
        .device_id = device_id,
        .user_id = login_message->actor_user_id,
        .session_id = login_message->session_id,
        .next_sequence = 2,
    };
}

std::optional<transport::GatewayResponseMessage> send_and_log(
    transport::SessionGatewayClient& gateway, const std::string& request_json) {
    std::cout << "[client] outbound " << request_json << '\n';
    if (const auto response = gateway.send_request_json(request_json); response.has_value()) {
        const auto message = gateway.parse_response_message(*response);
        if (!message.has_value()) {
            std::cout << "[client] failed to parse response payload\n";
            return std::nullopt;
        }
        std::cout << "[client] inbound " << message->raw_json << '\n';
        if (const auto* error = std::get_if<transport::ErrorResponsePayload>(&message->payload);
            error != nullptr) {
            std::cout << "[client] protocol error code=" << error->code
                      << " message=" << error->message << '\n';
        }
        return message;
    }
    std::cout << "[client] request failed while waiting for response\n";
    return std::nullopt;
}

void print_state_summary(const std::string& label, const ClientViewState& state) {
    std::cout << "[client] state " << label << " session=" << state.current_session_id
              << " user=" << state.current_user_id
              << " chat.devices=" << state.chat.device_count
              << " chat.conversations=" << state.chat.conversation_count
              << " chat.messages=" << state.chat.conversation_message_count
              << " chat.last_message_id=" << state.chat.last_message_id
              << " remote.session_id=" << state.remote.remote_session_id
              << " remote.state=" << state.remote.remote_session_state
              << " remote.relay_region=" << state.remote.relay_region
              << " remote.relay_endpoint=" << state.remote.relay_endpoint
              << " remote.candidates=" << state.remote.candidate_count
              << " last_error_code=" << state.last_error_code
              << " last_error=" << state.last_error_message << '\n';
}

}  // namespace

int AppShell::start() const {
    transport::SessionGatewayClient gateway;
    remote_control::RemoteSessionController remote;
    const bool state_changed =
        remote.apply_event(telegram_like::shared::protocol::RemoteSessionEvent::kSendInvite);

    std::cout << "[client] app shell starting\n";
    std::cout << "[client] " << gateway.describe() << '\n';
    std::cout << "[client] remote session bootstrap changed_state="
              << (state_changed ? "true" : "false") << '\n';
    std::cout << "[client] " << remote.describe() << '\n';

    if (!gateway.connect("127.0.0.1", 8787)) {
        std::cout << "[client] control plane unavailable on 127.0.0.1:8787\n";
        return 0;
    }

    ClientViewState alice_state;
    auto alice_session = login_user(gateway, "alice", "alice_pw", "dev_alice_win", "corr_login_1");
    if (!alice_session.has_value()) {
        std::cout << "[client] alice login failed\n";
        return 0;
    }
    alice_state.current_session_id = alice_session->session_id;
    alice_state.current_user_id = alice_session->user_id;
    print_state_summary("alice_after_login", alice_state);

    if (const auto summary = send_and_log(
            gateway,
            gateway.compose_request_json(transport::EmptyPayloadRequestMessage {
                .envelope = alice_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kConversationSync, "corr_sync_1"),
            }));
        summary.has_value()) {
        alice_state.apply_response(*summary);
        print_state_summary("alice_after_sync_1", alice_state);
    }

    if (const auto summary = send_and_log(
            gateway,
            gateway.compose_request_json(transport::EmptyPayloadRequestMessage {
                .envelope = alice_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kDeviceListRequest,
                    "corr_devices_1"),
            }));
        summary.has_value()) {
        alice_state.apply_response(*summary);
        print_state_summary("alice_after_devices", alice_state);
    }

    const auto message_send_json = gateway.compose_request_json(
        transport::MessageSendRequestMessage {
            .envelope = alice_session->make_envelope(
                telegram_like::shared::protocol::MessageType::kMessageSend, "corr_msg_1"),
            .conversation_id = "conv_alice_bob",
            .text = "hello from alice over persistent tcp control plane",
        });
    if (const auto summary = send_and_log(gateway, message_send_json); summary.has_value()) {
        alice_state.apply_response(*summary);
        print_state_summary("alice_after_send", alice_state);
    }

    if (const auto summary = send_and_log(
            gateway,
            gateway.compose_request_json(transport::EmptyPayloadRequestMessage {
                .envelope = alice_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kConversationSync, "corr_sync_2"),
            }));
        summary.has_value()) {
        alice_state.apply_response(*summary);
        print_state_summary("alice_after_sync_2", alice_state);
    }

    const telegram_like::shared::protocol::RemoteInvitePayload remote_invite_payload {
        .session_id = "remote_1",
        .requester_device_id = "dev_alice_win",
        .target_device_id = "dev_bob_win",
        .attended_session = true,
    };
    const auto remote_invite_json = gateway.compose_request_json(
        transport::RemoteInviteRequestMessage {
            .envelope = alice_session->make_envelope(
                telegram_like::shared::protocol::MessageType::kRemoteInvite, "corr_remote_1"),
            .payload = remote_invite_payload,
        });
    if (const auto remote_summary = send_and_log(gateway, remote_invite_json);
        remote_summary.has_value()) {
        alice_state.apply_response(*remote_summary);
        print_state_summary("alice_after_remote_invite", alice_state);

        gateway.disconnect();
        if (!gateway.connect("127.0.0.1", 8787)) {
            std::cout << "[client] reconnect failed for bob session\n";
            return 0;
        }

        ClientViewState bob_state;
        auto bob_session = login_user(gateway, "bob", "bob_pw", "dev_bob_win", "corr_login_2");
        if (!bob_session.has_value()) {
            std::cout << "[client] bob login failed\n";
            return 0;
        }
        bob_state.current_session_id = bob_session->session_id;
        bob_state.current_user_id = bob_session->user_id;
        bob_state.apply_response(*remote_summary);
        print_state_summary("bob_after_login", bob_state);

        if (const auto summary = send_and_log(
                gateway,
                gateway.compose_request_json(transport::EmptyPayloadRequestMessage {
                    .envelope = bob_session->make_envelope(
                        telegram_like::shared::protocol::MessageType::kConversationSync,
                        "corr_sync_3"),
                }));
            summary.has_value()) {
            bob_state.apply_response(*summary);
            print_state_summary("bob_after_sync", bob_state);
        }

        if (const auto summary = send_and_log(
                gateway,
                gateway.compose_request_json(transport::EmptyPayloadRequestMessage {
                    .envelope = bob_session->make_envelope(
                        telegram_like::shared::protocol::MessageType::kDeviceListRequest,
                        "corr_devices_2"),
                }));
            summary.has_value()) {
            bob_state.apply_response(*summary);
            print_state_summary("bob_after_devices", bob_state);
        }

        const auto remote_approve_json = gateway.compose_request_json(
            transport::RemoteApproveRequestMessage {
                .envelope = bob_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kRemoteApprove, "corr_remote_2"),
                .remote_session_id = bob_state.remote.remote_session_id,
            });
        if (const auto approve_summary = send_and_log(gateway, remote_approve_json);
            approve_summary.has_value()) {
            bob_state.apply_response(*approve_summary);
            print_state_summary("bob_after_remote_approve", bob_state);
        }

        const auto remote_rendezvous_json = gateway.compose_request_json(
            transport::RemoteSessionActionRequestMessage {
                .envelope = alice_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kRemoteRendezvousRequest,
                    "corr_remote_rdv"),
                .remote_session_id = bob_state.remote.remote_session_id,
            });
        if (const auto rendezvous_summary = send_and_log(gateway, remote_rendezvous_json);
            rendezvous_summary.has_value()) {
            alice_state.apply_response(*rendezvous_summary);
            print_state_summary("alice_after_rendezvous", alice_state);
        }

        if (const char* udp_port_env = std::getenv("TELEGRAM_LIKE_UDP_PORT");
            udp_port_env != nullptr && *udp_port_env != '\0') {
            const unsigned short udp_port =
                static_cast<unsigned short>(std::atoi(udp_port_env));
            const auto probe = transport::send_udp_probe(
                "127.0.0.1",
                udp_port,
                alice_state.current_session_id,
                "hello from alice media plane");
            if (probe.has_value()) {
                std::cout << "[client] udp probe ack=" << (probe->acked ? "yes" : "no")
                          << " bytes=" << probe->response_bytes.size()
                          << " text=" << probe->response_text << '\n';
            } else {
                std::cout << "[client] udp probe failed (timeout or server down)\n";
            }

            // Subscribe + collect structured frames.
            const auto stream = transport::subscribe_and_collect(
                "127.0.0.1",
                udp_port,
                alice_state.current_session_id,
                5,
                "demo");
            if (!stream.error.empty()) {
                std::cout << "[client] frame stream error: " << stream.error << '\n';
            }
            for (const auto& chunk : stream.frames) {
                std::cout << "[client] frame seq=" << chunk.seq
                          << " " << chunk.width << "x" << chunk.height
                          << " codec=" << static_cast<int>(chunk.codec)
                          << " ts=" << chunk.timestamp_ms
                          << "ms body_bytes=" << chunk.body.size() << '\n';
            }
        }

        const auto remote_terminate_json = gateway.compose_request_json(
            transport::RemoteSessionActionRequestMessage {
                .envelope = bob_session->make_envelope(
                    telegram_like::shared::protocol::MessageType::kRemoteTerminate, "corr_remote_3"),
                .remote_session_id = bob_state.remote.remote_session_id,
            });
        if (const auto terminate_summary = send_and_log(gateway, remote_terminate_json);
            terminate_summary.has_value()) {
            bob_state.apply_response(*terminate_summary);
            print_state_summary("bob_after_remote_terminate", bob_state);
        }
    }
    return 0;
}

}  // namespace telegram_like::client::app
