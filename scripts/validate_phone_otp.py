"""Validator for phone-number + OTP authentication (M90).

Drives an in-process ServerApplication through the request/verify flow with
the default MockSender so we can pluck the issued code from its outbox
instead of intercepting SMS.

Scenarios:
  1. request_code -> response with code_length=6 + ttl + MockSender records
     a (phone, code) entry.
  2. verify_code with the correct code -> session minted; user_id stable
     per phone; new_account=True the first time, False the second.
  3. Bad phone format -> INVALID_PHONE_NUMBER (e.g. missing leading +).
  4. verify_code with wrong code -> INVALID_OTP_CODE; after 5 wrong
     attempts -> OTP_ATTEMPTS_EXHAUSTED.
  5. request_code resend within 30s cooldown -> PHONE_OTP_RATE_LIMITED.
  6. expired code -> OTP_EXPIRED (drives the FakeClock past TTL).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def _request(app, phone, seq):
    return app.dispatch({
        **make_envelope(MessageType.PHONE_OTP_REQUEST, correlation_id=f"corr_otpr_{seq}", sequence=seq),
        "payload": {"phone_number": phone},
    })


def _verify(app, phone, code, device, display_name, seq):
    return app.dispatch({
        **make_envelope(MessageType.PHONE_OTP_VERIFY_REQUEST, correlation_id=f"corr_otpv_{seq}", sequence=seq),
        "payload": {
            "phone_number": phone,
            "code": code,
            "device_id": device,
            "display_name": display_name,
        },
    })


def scenario_request_then_verify_creates_account():
    print("[scenario] request -> verify -> session + new account")
    clock = FakeClock()
    app = ServerApplication(clock=clock)
    resp = _request(app, "+15551234567", 1)
    assert resp["type"] == "phone_otp_request_response", resp
    assert resp["payload"]["code_length"] == 6
    assert resp["payload"]["expires_in_seconds"] >= 60
    sender = app.phone_otp_service.sender
    code = sender.latest_for("+15551234567").code
    verify = _verify(app, "+15551234567", code, "dev_phone_a", "Carol", 2)
    assert verify["type"] == "phone_otp_verify_response", verify
    payload = verify["payload"]
    assert payload["new_account"] is True
    assert payload["display_name"] == "Carol"
    assert payload["session_id"] in app.state.sessions
    user_id = payload["user_id"]
    assert user_id == "u_phone_15551234567"
    # Second pass: same phone, no new account.
    clock.advance(60.0)
    _request(app, "+15551234567", 3)
    code2 = sender.latest_for("+15551234567").code
    verify2 = _verify(app, "+15551234567", code2, "dev_phone_a", "Carol Renamed", 4)
    assert verify2["payload"]["new_account"] is False
    assert verify2["payload"]["user_id"] == user_id
    print("[ok ] OTP request + verify round-trip")


def scenario_invalid_phone_number():
    print("[scenario] non-E.164 phone -> INVALID_PHONE_NUMBER")
    app = ServerApplication()
    for bad in ["", "5551234567", "+abc1234567", "+1"]:
        resp = _request(app, bad, 1)
        assert resp["type"] == "error", resp
        assert resp["payload"]["code"] == "invalid_phone_number", resp
    print("[ok ] bad phone numbers rejected")


def scenario_wrong_code_then_attempts_exhausted():
    print("[scenario] wrong code 5x -> OTP_ATTEMPTS_EXHAUSTED")
    app = ServerApplication()
    _request(app, "+15551234567", 1)
    for i in range(4):
        resp = _verify(app, "+15551234567", "000000", "dev_x", "", 2 + i)
        assert resp["type"] == "error", resp
        assert resp["payload"]["code"] == "invalid_otp_code", resp
    last = _verify(app, "+15551234567", "000000", "dev_x", "", 6)
    assert last["payload"]["code"] == "otp_attempts_exhausted", last
    # Even with the right code, attempts are exhausted now.
    real = app.phone_otp_service.sender.latest_for("+15551234567").code
    after = _verify(app, "+15551234567", real, "dev_x", "", 7)
    assert after["payload"]["code"] == "otp_attempts_exhausted", after
    print("[ok ] attempts cap fires + locks subsequent verifies")


def scenario_resend_cooldown():
    print("[scenario] re-request within 30s cooldown -> PHONE_OTP_RATE_LIMITED")
    clock = FakeClock()
    app = ServerApplication(clock=clock)
    _request(app, "+15551234567", 1)
    resp = _request(app, "+15551234567", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "phone_otp_rate_limited", resp
    # After cooldown elapses, request succeeds.
    clock.advance(31.0)
    ok = _request(app, "+15551234567", 3)
    assert ok["type"] == "phone_otp_request_response", ok
    print("[ok ] cooldown enforced + lifts after 30s")


def scenario_expired_code():
    print("[scenario] verify after TTL -> OTP_EXPIRED")
    clock = FakeClock()
    app = ServerApplication(clock=clock)
    _request(app, "+15551234567", 1)
    code = app.phone_otp_service.sender.latest_for("+15551234567").code
    clock.advance(301.0)  # past TTL
    resp = _verify(app, "+15551234567", code, "dev_x", "", 2)
    assert resp["type"] == "error", resp
    assert resp["payload"]["code"] == "otp_expired", resp
    print("[ok ] expired code rejected")


def main() -> int:
    scenarios = [
        scenario_request_then_verify_creates_account,
        scenario_invalid_phone_number,
        scenario_wrong_code_then_attempts_exhausted,
        scenario_resend_cooldown,
        scenario_expired_code,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
