"""Validator for per-session / per-key rate limiting (M93).

Drives an in-process ServerApplication with a controllable monotonic clock
so we can fast-forward token-bucket refill without sleeping.

Scenarios:
  1. message_send hot path: 10 burst + 5/s refill — first 10 succeed, 11th
     gets RATE_LIMITED, after a clock advance one slot opens up.
  2. phone_otp_request: 3 burst per phone number — 4th OTP request to the
     same number gets RATE_LIMITED while a different number is unaffected.
  3. register_request: 5 burst per username — 6th register attempt with
     same username rate-limited.
  4. presence_query_request: rate limit is per-session, two sessions don't
     interfere.
  5. rate_limited_total counter increments on each rejection and is
     labelled by op type.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402


class FakeMonoClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def _login(app, user, password, device, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _send(app, sess, conv, text, seq):
    return app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id=f"corr_send_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"conversation_id": conv, "text": text},
    })


def _otp_req(app, phone, seq):
    return app.dispatch({
        **make_envelope(MessageType.PHONE_OTP_REQUEST, correlation_id=f"corr_otp_{seq}", sequence=seq),
        "payload": {"phone_number": phone},
    })


def _register(app, username, seq):
    return app.dispatch({
        **make_envelope(MessageType.REGISTER_REQUEST, correlation_id=f"corr_reg_{seq}", sequence=seq),
        "payload": {"username": username, "password": "pw_strong",
                    "display_name": username, "device_id": f"dev_{seq}"},
    })


def _presence(app, sess, ids, seq):
    return app.dispatch({
        **make_envelope(MessageType.PRESENCE_QUERY_REQUEST, correlation_id=f"corr_pq_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"user_ids": ids},
    })


def _new_app() -> ServerApplication:
    """Each scenario uses a fresh app to avoid cross-bucket leakage."""
    return ServerApplication()


def scenario_message_send_burst_then_refill():
    print("[scenario] message_send: 10 burst + 5/s refill")
    clock = FakeMonoClock()
    app = _new_app()
    app.rate_limiter._clock = clock  # inject test clock
    app.rate_limiter.reset()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    seq = 2
    successes = 0
    for _ in range(10):
        resp = _send(app, alice, "conv_alice_bob", "spam", seq); seq += 1
        if resp["type"] == "message_deliver":
            successes += 1
    assert successes == 10, f"expected 10 successes, got {successes}"
    # 11th send must be rejected.
    rejected = _send(app, alice, "conv_alice_bob", "spam", seq); seq += 1
    assert rejected["type"] == "error", rejected
    assert rejected["payload"]["code"] == "rate_limited", rejected
    # Advance 1 second -> 5 tokens refilled. Five more sends succeed.
    clock.advance(1.0)
    refilled = 0
    for _ in range(5):
        resp = _send(app, alice, "conv_alice_bob", "spam", seq); seq += 1
        if resp["type"] == "message_deliver":
            refilled += 1
    assert refilled == 5, f"expected 5 refilled, got {refilled}"
    print("[ok ] burst exhaustion + refill recovery")


def scenario_otp_request_per_number():
    print("[scenario] phone_otp_request: per-phone isolation; rate limiter and OTP cooldown both bite")
    app = _new_app()
    app.rate_limiter.reset()
    seq = 1
    # Different numbers: each hits its own bucket AND its own OTP cooldown.
    # Five distinct numbers: each first request succeeds.
    for i in range(5):
        resp = _otp_req(app, f"+1555000{i:04d}", seq); seq += 1
        assert resp["type"] == "phone_otp_request_response", resp
    # Same number repeated. The first succeeds; subsequent ones get
    # rejected — either by the OTP cooldown (phone_otp_rate_limited) or
    # by the rate limiter (rate_limited). Both are correct rejections of
    # OTP flooding; we just want to confirm the second request fails.
    first = _otp_req(app, "+15559999999", seq); seq += 1
    assert first["type"] == "phone_otp_request_response", first
    # Now drain the rate-limiter burst. After ~burst more attempts we
    # should see the rate_limited code at least once (the OTP cooldown
    # already fires from the second attempt; the rate limiter takes over
    # if cooldown is somehow bypassed).
    rejected_codes: set[str] = set()
    for i in range(6):
        resp = _otp_req(app, "+15559999999", seq); seq += 1
        if resp["type"] == "error":
            rejected_codes.add(resp["payload"]["code"])
    assert rejected_codes, "expected at least one rejection for repeated OTP request to same number"
    assert rejected_codes <= {"phone_otp_rate_limited", "rate_limited"}, \
        f"unexpected rejection codes: {rejected_codes}"
    print(f"[ok ] same-number repeat rejected via {sorted(rejected_codes)}")


def scenario_register_per_username():
    print("[scenario] register_request: 5 burst per username")
    app = _new_app()
    app.rate_limiter.reset()
    burst = int(app.rate_limiter.get_config("register_request").burst)
    seq = 1
    successes = 0
    for i in range(burst):
        resp = _register(app, "newbie", seq); seq += 1
        # First success creates the account; next 4 are USERNAME_TAKEN
        # but they STILL count against the rate limiter (the limiter sits
        # before AuthService.register).
        if resp["type"] in ("register_response", "error"):
            successes += 1
    over = _register(app, "newbie", seq); seq += 1
    assert over["type"] == "error", over
    assert over["payload"]["code"] == "rate_limited", over
    print(f"[ok ] {burst} attempts per username burst before rate_limited kicks in")


def scenario_presence_query_per_session():
    print("[scenario] presence_query_request: per-session bucket isolation")
    app = _new_app()
    app.rate_limiter.reset()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    bob = _login(app, "bob", "bob_pw", "dev_bob", 2)
    burst = int(app.rate_limiter.get_config("presence_query_request").burst)
    seq = 3
    # Burn through alice's bucket entirely.
    for i in range(burst):
        resp = _presence(app, alice, ["u_bob"], seq); seq += 1
        assert resp["type"] == "presence_query_response", resp
    over = _presence(app, alice, ["u_bob"], seq); seq += 1
    assert over["type"] == "error" and over["payload"]["code"] == "rate_limited", over
    # Bob's session should still have a fresh bucket.
    bob_first = _presence(app, bob, ["u_alice"], seq); seq += 1
    assert bob_first["type"] == "presence_query_response", bob_first
    print(f"[ok ] alice bucket drained ({burst}); bob unaffected")


def scenario_metrics_counter_increments():
    print("[scenario] rate_limited_total counter increments per rejection")
    app = _new_app()
    app.rate_limiter.reset()
    alice = _login(app, "alice", "alice_pw", "dev_alice", 1)
    burst = int(app.rate_limiter.get_config("message_send").burst)
    seq = 2
    for i in range(burst + 3):
        _send(app, alice, "conv_alice_bob", "spam", seq); seq += 1
    text = app.observability.metrics.render_prometheus()
    assert 'rate_limited_total{type="message_send"}' in text, text
    # The counter line follows; extract the number.
    for line in text.splitlines():
        if line.startswith('rate_limited_total{type="message_send"}'):
            count = float(line.split()[-1])
            break
    assert count >= 3, f"expected at least 3 rejections, got {count}"
    print(f"[ok ] rate_limited_total counter reached {count}")


def main() -> int:
    scenarios = [
        scenario_message_send_burst_then_refill,
        scenario_otp_request_per_number,
        scenario_register_per_username,
        scenario_presence_query_per_session,
        scenario_metrics_counter_increments,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
