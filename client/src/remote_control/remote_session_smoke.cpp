// Minimal C++ smoke for the new ControlPlaneClient remote-control RPCs.
//
// We log in, then call each new method against the server with arguments that
// produce a *legitimate error response* (e.g. terminating a session that
// doesn't exist). This proves:
//   - the request envelopes serialize correctly,
//   - the server dispatches them,
//   - the response parsers handle the typed error frame without crashing.
//
// Driven by scripts/validate_cpp_remote_session.py; expects a Python server
// on --host/--port and a registered alice/alice_pw account already created
// by the validator.
#include "transport/control_plane_client.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

using telegram_like::client::transport::ControlPlaneClient;

namespace {

struct Args {
    std::string user = "alice";
    std::string password = "alice_pw";
    std::string device = "dev_remote_smoke";
    std::string host = "127.0.0.1";
    unsigned short port = 8787;
};

bool parse_args(int argc, char** argv, Args& out) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "missing value for " << name << "\n";
                return nullptr;
            }
            return argv[++i];
        };
        if (a == "--user") { auto v = next("--user"); if (!v) return false; out.user = v; }
        else if (a == "--password") { auto v = next("--password"); if (!v) return false; out.password = v; }
        else if (a == "--device") { auto v = next("--device"); if (!v) return false; out.device = v; }
        else if (a == "--host") { auto v = next("--host"); if (!v) return false; out.host = v; }
        else if (a == "--port") { auto v = next("--port"); if (!v) return false; out.port = static_cast<unsigned short>(std::atoi(v)); }
        else { std::cerr << "unknown arg: " << a << "\n"; return false; }
    }
    return true;
}

int fail(const char* tag, const std::string& detail) {
    std::cerr << "[FAIL] " << tag << ": " << detail << "\n";
    return 1;
}

}  // namespace

int main(int argc, char** argv) {
    Args args;
    if (!parse_args(argc, argv, args)) return 2;

    ControlPlaneClient client;
    if (!client.connect(args.host, args.port)) {
        return fail("connect", "could not open TCP connection");
    }
    const auto login = client.login(args.user, args.password, args.device);
    if (!login.ok) return fail("login", login.error_code + " " + login.error_message);

    int passed = 0;
    int total = 0;

    // 1. remote_invite to a non-existent target device — expect error.
    ++total;
    {
        const auto r = client.remote_invite(args.device, "nonexistent_target_device");
        if (r.ok || r.error_code.empty()) {
            return fail("remote_invite_negative", "expected error, got ok=" + std::to_string(r.ok));
        }
        std::cout << "[ok ] remote_invite negative path: " << r.error_code << "\n";
        ++passed;
    }

    // 2. remote_approve fake session id — expect error.
    ++total;
    {
        const auto r = client.remote_approve("rs_does_not_exist");
        if (r.ok || r.error_code.empty()) {
            return fail("remote_approve_negative", "expected error");
        }
        std::cout << "[ok ] remote_approve negative path: " << r.error_code << "\n";
        ++passed;
    }

    // 3-6. terminal-action variants on a fake session — each must return error.
    for (const auto& [tag, action] : std::initializer_list<std::pair<const char*, std::string>>{
             {"remote_reject", "reject"},
             {"remote_cancel", "cancel"},
             {"remote_terminate", "terminate"},
             {"remote_disconnect", "disconnect"}}) {
        ++total;
        ControlPlaneClient::PushHandler dummy;
        (void)dummy;
        telegram_like::client::transport::RemoteSessionTerminatedResult r;
        if (action == "reject") r = client.remote_reject("rs_fake");
        else if (action == "cancel") r = client.remote_cancel("rs_fake");
        else if (action == "terminate") r = client.remote_terminate("rs_fake");
        else r = client.remote_disconnect("rs_fake", "smoke");
        if (r.ok || r.error_code.empty()) {
            return fail(tag, "expected error");
        }
        std::cout << "[ok ] " << tag << " negative path: " << r.error_code << "\n";
        ++passed;
    }

    // 7. remote_rendezvous_request on fake session — expect error.
    ++total;
    {
        const auto r = client.remote_rendezvous_request("rs_fake");
        if (r.ok || r.error_code.empty()) {
            return fail("remote_rendezvous_request_negative", "expected error");
        }
        std::cout << "[ok ] remote_rendezvous_request negative path: " << r.error_code << "\n";
        ++passed;
    }

    // 8. remote_input_event on fake session — expect error.
    ++total;
    {
        const auto r = client.remote_input_event("rs_fake", "key", "{\"key\":\"a\"}");
        if (r.ok || r.error_code.empty()) {
            return fail("remote_input_event_negative", "expected error");
        }
        std::cout << "[ok ] remote_input_event negative path: " << r.error_code << "\n";
        ++passed;
    }

    std::cout << "passed " << passed << "/" << total << "\n";
    return passed == total ? 0 : 1;
}
