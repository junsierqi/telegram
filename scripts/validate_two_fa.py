"""Validator for TOTP 2FA (M94).

Drives the in-process ServerApplication through enroll → verify → login →
disable using stdlib-generated TOTP codes (no third-party deps).

Scenarios:
  1. begin_enable returns secret + otpauth provisioning URI.
  2. verify_enable with the correct code flips two_fa_secret on the user.
  3. login without two_fa_code while 2FA is on -> TWO_FA_REQUIRED.
  4. login with WRONG two_fa_code -> INVALID_TWO_FA_CODE.
  5. login with correct two_fa_code -> session issued.
  6. disable requires a fresh code; once disabled, login again works without one.
  7. begin_enable when already enabled -> TWO_FA_ALREADY_ENABLED.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.two_fa import generate_totp_code  # noqa: E402


def _login(app, user, password, device, seq, two_fa_code: str = ""):
    return app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {
            "username": user, "password": password, "device_id": device,
            "two_fa_code": two_fa_code,
        },
    })


def _enable_request(app, sess, seq):
    return app.dispatch({
        **make_envelope(MessageType.TWO_FA_ENABLE_REQUEST, correlation_id=f"corr_2fa_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {},
    })


def _verify_enable(app, sess, code, seq):
    return app.dispatch({
        **make_envelope(MessageType.TWO_FA_VERIFY_REQUEST, correlation_id=f"corr_2fa_v_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"code": code},
    })


def _disable(app, sess, code, seq):
    return app.dispatch({
        **make_envelope(MessageType.TWO_FA_DISABLE_REQUEST, correlation_id=f"corr_2fa_d_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"code": code},
    })


def scenario_full_lifecycle():
    print("[scenario] enroll -> verify -> login required -> disable")
    app = ServerApplication()
    login = _login(app, "alice", "alice_pw", "dev_alice", 1)
    assert login["type"] == "login_response", login
    alice = login["payload"]
    # 1. begin_enable
    enr = _enable_request(app, alice, 2)
    assert enr["type"] == "two_fa_enable_response", enr
    secret = enr["payload"]["secret"]
    uri = enr["payload"]["provisioning_uri"]
    assert secret and uri.startswith("otpauth://totp/"), uri
    # 2. verify_enable with the right code (computed via stdlib helper)
    code = generate_totp_code(secret)
    ver = _verify_enable(app, alice, code, 3)
    assert ver["type"] == "two_fa_verify_response", ver
    assert ver["payload"]["enabled"] is True
    # 3. fresh login without two_fa_code -> TWO_FA_REQUIRED
    bad = _login(app, "alice", "alice_pw", "dev_alice_2", 4)
    assert bad["type"] == "error" and bad["payload"]["code"] == "two_fa_required", bad
    # 4. login with wrong code -> INVALID_TWO_FA_CODE
    wrong = _login(app, "alice", "alice_pw", "dev_alice_2", 5, two_fa_code="000000")
    assert wrong["type"] == "error" and wrong["payload"]["code"] == "invalid_two_fa_code", wrong
    # 5. login with correct code -> session issued
    fresh_code = generate_totp_code(secret)
    ok = _login(app, "alice", "alice_pw", "dev_alice_2", 6, two_fa_code=fresh_code)
    assert ok["type"] == "login_response", ok
    new_session = ok["payload"]["session_id"]
    assert new_session in app.state.sessions
    # 6. disable: needs fresh code, then login again works without it
    code2 = generate_totp_code(secret)
    disabled = _disable(app, alice, code2, 7)
    assert disabled["type"] == "two_fa_disable_response", disabled
    assert disabled["payload"]["enabled"] is False
    plain = _login(app, "alice", "alice_pw", "dev_alice_3", 8)
    assert plain["type"] == "login_response", plain
    print("[ok ] full enroll → login-required → disable lifecycle")


def scenario_double_enable_rejected():
    print("[scenario] begin_enable when already enabled -> TWO_FA_ALREADY_ENABLED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    enr = _enable_request(app, alice, 2)
    secret = enr["payload"]["secret"]
    _verify_enable(app, alice, generate_totp_code(secret), 3)
    again = _enable_request(app, alice, 4)
    assert again["type"] == "error", again
    assert again["payload"]["code"] == "two_fa_already_enabled", again
    print("[ok ] re-enable rejected")


def scenario_disable_without_2fa_rejected():
    print("[scenario] disable when never enabled -> TWO_FA_NOT_ENABLED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    resp = _disable(app, alice, "000000", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "two_fa_not_enabled", resp
    print("[ok ] disable without 2FA rejected")


def scenario_verify_without_pending_rejected():
    print("[scenario] verify_enable without prior begin_enable -> TWO_FA_NOT_ENABLED")
    app = ServerApplication()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)["payload"]
    resp = _verify_enable(app, alice, "000000", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "two_fa_not_enabled", resp
    print("[ok ] verify without enrollment rejected")


def main() -> int:
    scenarios = [
        scenario_full_lifecycle,
        scenario_double_enable_rejected,
        scenario_disable_without_2fa_rejected,
        scenario_verify_without_pending_rejected,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
