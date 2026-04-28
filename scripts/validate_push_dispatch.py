"""Validator for the push dispatch worker (M91).

Drives the in-memory ServerApplication.push_token_service queue through
real worker.tick() calls with FakeTransport, LogOnlyTransport, and the
FCMHttpTransport in dry-run mode (no network).

Scenarios:
  1. tick() with empty queue returns an empty report.
  2. Per-platform routing: registering a token under platform="fcm" and
     another under "apns" → tick() sends each batch to its own transport.
  3. Default fallback: a platform with no registered transport uses the
     default (LogOnlyTransport here).
  4. FCMHttpTransport.dry_run records the request payload without POSTing.
  5. End-to-end: server enqueues a mock push for an offline recipient,
     worker.tick() routes it through the registered FakeTransport.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.push_dispatch import (  # noqa: E402
    FakeTransport,
    FCMHttpTransport,
    LogOnlyTransport,
    PushDispatchWorker,
)
from server.server.services.push_tokens import PendingDelivery  # noqa: E402


def _login(app, user, password, device, seq):
    resp = app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })
    assert resp["type"] == "login_response", resp
    return resp["payload"]


def _push_register(app, sess, platform, token, seq):
    return app.dispatch({
        **make_envelope(MessageType.PUSH_TOKEN_REGISTER, correlation_id=f"corr_pr_{seq}",
                        session_id=sess["session_id"], actor_user_id=sess["user_id"], sequence=seq),
        "payload": {"platform": platform, "token": token},
    })


def scenario_empty_queue_yields_empty_report():
    print("[scenario] worker.tick() on empty queue -> empty report")
    app = ServerApplication()
    fake = FakeTransport(name="fake")
    worker = PushDispatchWorker(app.push_token_service,
                                transport_for=lambda p: fake)
    report = worker.tick()
    assert report.total() == 0
    assert fake.received == []
    print("[ok ] empty queue is a no-op")


def scenario_per_platform_routing():
    print("[scenario] tick routes each platform batch to its own transport")
    app = ServerApplication()
    fcm = FakeTransport(name="fcm")
    apns = FakeTransport(name="apns")
    transports = {"fcm": fcm, "apns": apns}
    worker = PushDispatchWorker(
        app.push_token_service,
        transport_for=lambda p: transports.get(p),
        default_transport=LogOnlyTransport("dropped", stream=io.StringIO()),
    )
    # Manually enqueue to skip the message-flow round-trip — we're testing
    # the dispatch routing itself.
    app.push_token_service.pending_deliveries.extend([
        PendingDelivery(user_id="u_a", device_id="d_a", platform="fcm",
                        token="fcm-aaa", kind="message_deliver",
                        body_summary="hi", enqueued_at_ms=0),
        PendingDelivery(user_id="u_b", device_id="d_b", platform="apns",
                        token="apns-bbb", kind="message_deliver",
                        body_summary="hi", enqueued_at_ms=0),
        PendingDelivery(user_id="u_c", device_id="d_c", platform="fcm",
                        token="fcm-ccc", kind="message_deliver",
                        body_summary="hi", enqueued_at_ms=0),
    ])
    report = worker.tick()
    assert report.total() == 3
    assert len(report.successful) == 3
    assert len(fcm.received) == 2
    assert len(apns.received) == 1
    assert {d.token for d in fcm.received} == {"fcm-aaa", "fcm-ccc"}
    assert apns.received[0].token == "apns-bbb"
    print("[ok ] fcm batch=2, apns batch=1, all delivered")


def scenario_default_fallback_used_when_no_transport():
    print("[scenario] platform with no registered transport falls back to default")
    app = ServerApplication()
    sink = io.StringIO()
    default = LogOnlyTransport("default-log", stream=sink)
    worker = PushDispatchWorker(
        app.push_token_service,
        transport_for=lambda p: None,  # nothing registered
        default_transport=default,
    )
    app.push_token_service.pending_deliveries.append(
        PendingDelivery(user_id="u_x", device_id="d_x", platform="exotic",
                        token="t-x", kind="message_deliver",
                        body_summary="hi", enqueued_at_ms=0)
    )
    report = worker.tick()
    assert report.total() == 1
    assert "default-log" in sink.getvalue()
    print("[ok ] fallback transport used when platform has no specific transport")


def scenario_fcm_http_transport_dry_run():
    print("[scenario] FCMHttpTransport in dry_run records payload without POSTing")
    fcm = FCMHttpTransport(project_id="fake-project", bearer_token="",
                           dry_run=True)
    assert fcm.dry_run is True  # forced True by missing bearer
    deliveries = [
        PendingDelivery(user_id="u_a", device_id="d_a", platform="fcm",
                        token="fcm-aaa", kind="message_deliver",
                        body_summary="hi alice", enqueued_at_ms=0),
    ]
    attempts = fcm.send(deliveries)
    assert len(attempts) == 1
    assert attempts[0].success is True
    assert attempts[0].detail == "dry_run"
    assert len(fcm.dry_run_payloads) == 1
    payload = fcm.dry_run_payloads[0]
    assert payload["message"]["token"] == "fcm-aaa"
    assert "Telegram-like" in payload["message"]["notification"]["title"]
    assert payload["message"]["notification"]["body"] == "hi alice"
    print("[ok ] dry-run payload has shape FCM v1 expects")


def scenario_end_to_end_offline_send_through_worker():
    print("[scenario] message_send to offline user -> worker.tick() delivers via FakeTransport")
    app = ServerApplication(presence_ttl_seconds=5.0)
    bob = _login(app, "bob", "bob_pw", "dev_bob", 1)
    _push_register(app, bob, "fcm", "fcm_token_bob", 2)
    # Drop bob's session so he's offline.
    del app.state.sessions[bob["session_id"]]
    alice = _login(app, "alice", "alice_pw", "dev_alice", 3)
    fake = FakeTransport(name="fcm")
    worker = PushDispatchWorker(app.push_token_service,
                                transport_for=lambda p: fake if p == "fcm" else None)
    # Alice sends a message into the seed conversation; server enqueues
    # a mock push for offline bob.
    app.dispatch({
        **make_envelope(MessageType.MESSAGE_SEND, correlation_id="corr_ms",
                        session_id=alice["session_id"], actor_user_id=alice["user_id"],
                        sequence=4),
        "payload": {"conversation_id": "conv_alice_bob", "text": "hey while offline"},
    })
    report = worker.tick()
    assert report.total() == 1
    assert len(fake.received) == 1
    delivered = fake.received[0]
    assert delivered.user_id == "u_bob"
    assert delivered.token == "fcm_token_bob"
    assert "while offline" in delivered.body_summary
    # Second tick must be a no-op: worker drained the queue.
    second = worker.tick()
    assert second.total() == 0
    print("[ok ] end-to-end offline -> queue -> worker -> transport")


def main() -> int:
    scenarios = [
        scenario_empty_queue_yields_empty_report,
        scenario_per_platform_routing,
        scenario_default_fallback_used_when_no_transport,
        scenario_fcm_http_transport_dry_run,
        scenario_end_to_end_offline_send_through_worker,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
