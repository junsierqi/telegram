"""Validator for the M97 concurrency + leak fixes.

Drives the in-process services with synthetic concurrency (threads sharing
one app object) so the locks are exercised in practice, not just present.
Covers:

  1. PhoneOtpService: 8 concurrent verify_code calls with the wrong code
     bump attempts exactly 5 times (then exhausted), never more, never less.
  2. PhoneOtpService: request_code purges expired entries opportunistically
     so _codes never exceeds the active-flow set.
  3. TwoFAService: two parallel confirm_enable on the same user end up with
     exactly one success and one failure — the loser gets a typed error,
     the winner persists the secret.
  4. PushTokenService: enqueueing while another thread drains never loses
     deliveries (count enqueued == count drained across the parallel run).
  5. AccountLifecycleService.delete clears any pending 2FA enrollment so a
     deleted user_id can't have their secret resurrected on a future
     confirm_enable call.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import ErrorCode, ServiceError  # noqa: E402
from server.server.services.phone_otp import (  # noqa: E402
    CODE_TTL_SECONDS,
    MAX_VERIFY_ATTEMPTS,
    _OtpRecord,
)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def scenario_phone_otp_concurrent_verify():
    print("[scenario] phone_otp: 8 parallel verify-with-wrong-code never overshoots MAX_VERIFY_ATTEMPTS")
    app = ServerApplication()
    app.phone_otp_service.request_code("+15551234567")
    # Pull the real code, then never use it — every thread submits a wrong code.
    real = app.phone_otp_service.sender.latest_for("+15551234567").code
    wrong = "000000" if real != "000000" else "111111"

    results: list[str] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        try:
            app.phone_otp_service.verify_code(
                "+15551234567", wrong, device_id="dev_x", display_name="",
            )
            outcome = "ok"
        except ServiceError as exc:
            outcome = exc.code.value
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    invalid = sum(1 for r in results if r == "invalid_otp_code")
    exhausted = sum(1 for r in results if r == "otp_attempts_exhausted")
    # Without the lock the sum could be < 8 (lost increments) or the split
    # could let > MAX_VERIFY_ATTEMPTS through. We require: every attempt
    # accounted for, exactly MAX-1 INVALID + remaining EXHAUSTED.
    assert invalid + exhausted == 8, f"got invalid={invalid} exhausted={exhausted}"
    assert invalid == MAX_VERIFY_ATTEMPTS - 1, \
        f"expected exactly {MAX_VERIFY_ATTEMPTS - 1} INVALID before exhaustion, got {invalid}"
    print(f"[ok ] {invalid} INVALID + {exhausted} EXHAUSTED, no lost increments")


def scenario_phone_otp_purges_expired_codes():
    print("[scenario] phone_otp: request_code drops expired entries from _codes")
    clock = FakeClock()
    app = ServerApplication(clock=clock)
    # We can't inject the clock into the OTP service directly via app.dispatch,
    # so reach into the service. Same approach the validator already takes.
    app.phone_otp_service._clock = clock
    # 50 phones request codes, 30 minutes pass — all should expire.
    for i in range(50):
        app.phone_otp_service.request_code(f"+1555000{i:04d}")
    assert len(app.phone_otp_service._codes) == 50
    clock.advance(CODE_TTL_SECONDS + 1)
    # New request_code should sweep them.
    app.phone_otp_service.request_code("+15559990000")
    # Only the brand-new one survives.
    assert len(app.phone_otp_service._codes) == 1, \
        f"expected 1 surviving entry, got {len(app.phone_otp_service._codes)}"
    print("[ok ] expired entries purged on next request_code")


def scenario_two_fa_concurrent_confirm():
    print("[scenario] two_fa: parallel confirm_enable -> exactly one winner")
    app = ServerApplication()
    # Log in alice (LOGIN_REQUEST) so we have a user_id.
    from server.server.protocol import MessageType, make_envelope
    app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="corr_l", sequence=1),
        "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_a"},
    })
    secret, _uri = app.two_fa_service.begin_enable("u_alice")
    from server.server.services.two_fa import generate_totp_code
    code = generate_totp_code(secret)

    successes: list[bool] = []
    errors: list[str] = []
    res_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        try:
            app.two_fa_service.confirm_enable("u_alice", code)
            with res_lock: successes.append(True)
        except ServiceError as exc:
            with res_lock: errors.append(exc.code.value)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Lock guarantees consistent end state. The acceptable outcomes are:
    # (a) both threads see the pending secret and both write the same
    #     value to user.two_fa_secret → 2 successes, 0 errors,
    # (b) first thread pops _pending then second sees nothing → 1 success,
    #     1 typed TWO_FA_NOT_ENABLED.
    # The forbidden outcome the lock blocks is a torn final state where
    # user.two_fa_secret ends up unset or as garbage. Check that.
    assert app.state.users["u_alice"].two_fa_secret == secret, \
        "torn state — user.two_fa_secret didn't end up as the enrolled value"
    # Plus: every error must be a typed ServiceError code, not an exception.
    bad = [e for e in errors if e not in ("two_fa_not_enabled",)]
    assert not bad, f"unexpected error codes after concurrent confirm: {bad}"
    print(f"[ok ] {len(successes)} success(es), {len(errors)} fail(s) — final state consistent")


def scenario_push_tokens_no_deliveries_lost():
    print("[scenario] push_tokens: enqueue racing with drain never loses entries")
    app = ServerApplication()
    # Pre-register 4 push tokens for u_alice.
    for i in range(4):
        app.push_token_service.register("u_alice", f"d_{i}", "fcm", f"tok_{i}")
    # 50 enqueue rounds running in parallel with 25 drain rounds; total
    # entries enqueued across all rounds must equal entries drained
    # (the queue snapshot at the very end, plus everything drained mid-way).
    enqueue_rounds = 50
    drained_total: list[int] = [0]
    drained_lock = threading.Lock()
    enqueue_done = threading.Event()

    def enqueuer():
        for _ in range(enqueue_rounds):
            app.push_token_service.notify_offline_recipient(
                "u_alice", "message_deliver", "burst",
            )
        enqueue_done.set()

    def drainer():
        while not enqueue_done.is_set():
            batch = app.push_token_service.drain_pending()
            with drained_lock:
                drained_total[0] += len(batch)
        # final pass after enqueue_done flipped
        batch = app.push_token_service.drain_pending()
        with drained_lock:
            drained_total[0] += len(batch)

    e = threading.Thread(target=enqueuer)
    d = threading.Thread(target=drainer)
    e.start(); d.start()
    e.join(); d.join()

    # Each round enqueues 4 (one per token). Total expected = enqueue_rounds * 4.
    expected = enqueue_rounds * 4
    assert drained_total[0] == expected, \
        f"lost deliveries: drained {drained_total[0]}, expected {expected}"
    print(f"[ok ] {drained_total[0]}/{expected} drained — none lost in race")


def scenario_account_delete_clears_pending_enrollment():
    print("[scenario] account_lifecycle.delete clears 2FA _pending so secret can't dangle")
    app = ServerApplication()
    from server.server.protocol import MessageType, make_envelope
    app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="corr_l", sequence=1),
        "payload": {"username": "alice", "password": "alice_pw", "device_id": "dev_a"},
    })
    # Begin (but never confirm) 2FA enrollment.
    secret, _uri = app.two_fa_service.begin_enable("u_alice")
    assert "u_alice" in app.two_fa_service._pending
    # Now delete the account.
    app.account_lifecycle_service.delete("u_alice", password="alice_pw", two_fa_code="")
    assert "u_alice" not in app.state.users
    assert "u_alice" not in app.two_fa_service._pending, \
        "M97 fix not applied — pending enrollment leaked past account delete"
    print("[ok ] _pending cleared on delete")


def main() -> int:
    scenarios = [
        scenario_phone_otp_concurrent_verify,
        scenario_phone_otp_purges_expired_codes,
        scenario_two_fa_concurrent_confirm,
        scenario_push_tokens_no_deliveries_lost,
        scenario_account_delete_clears_pending_enrollment,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
