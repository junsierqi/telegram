"""Validator for observability primitives (M92).

Drives the in-process Observability + ServerApplication to verify:

  1. dispatch() emits dispatch_requests_total counter + a duration histogram.
  2. /metrics HTTP endpoint serves Prometheus exposition format.
  3. /healthz returns 200 + JSON when all checks pass.
  4. /healthz returns 503 when any check fails.
  5. Structured logger emits valid JSON lines.
  6. Counter labels separate ok / error outcomes correctly.
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
from pathlib import Path

# Bypass any system HTTP_PROXY for 127.0.0.1 requests in this validator —
# corporate proxies that hairpin localhost traffic return spurious 5xx.
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.server.app import ServerApplication  # noqa: E402
from server.server.protocol import MessageType, make_envelope  # noqa: E402
from server.server.services.observability import Observability  # noqa: E402


def _login(app, user, password, device, seq):
    return app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id=f"corr_login_{seq}", sequence=seq),
        "payload": {"username": user, "password": password, "device_id": device},
    })


def scenario_dispatch_emits_counter_and_histogram():
    print("[scenario] dispatch() bumps dispatch_requests_total + duration histogram")
    app = ServerApplication()
    _login(app, "alice", "alice_pw", "dev_alice", 1)
    text = app.observability.metrics.render_prometheus()
    assert "dispatch_requests_total" in text
    assert 'type="login_request"' in text and 'outcome="ok"' in text
    assert "dispatch_request_duration_seconds_sum" in text
    assert "dispatch_request_duration_seconds_count" in text
    print("[ok ] login_request + ok outcome counted, latency observed")


def scenario_metrics_endpoint_serves_prometheus():
    print("[scenario] GET /metrics serves Prometheus text exposition")
    app = ServerApplication()
    _login(app, "alice", "alice_pw", "dev_alice", 1)
    port = app.observability.start_http(host="127.0.0.1", port=0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
            assert resp.getcode() == 200
            ct = resp.headers["Content-Type"]
            assert "text/plain" in ct, ct
            body = resp.read().decode("utf-8")
        assert "# TYPE dispatch_requests_total counter" in body
        assert "# TYPE dispatch_request_duration_seconds histogram" in body
    finally:
        app.observability.stop_http()
    print("[ok ] /metrics serves valid exposition")


def scenario_healthz_ok_when_all_checks_pass():
    print("[scenario] GET /healthz returns 200 when all checks pass")
    app = ServerApplication()
    port = app.observability.start_http(host="127.0.0.1", port=0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as resp:
            assert resp.getcode() == 200
            body = json.loads(resp.read().decode("utf-8"))
        assert body["ok"] is True
        names = {c["name"] for c in body["checks"]}
        assert "state_loaded" in names
        assert "active_session_count" in names
    finally:
        app.observability.stop_http()
    print("[ok ] /healthz 200 + lists registered checks")


def scenario_healthz_failing_check_returns_503():
    print("[scenario] /healthz returns 503 when a check fails")
    app = ServerApplication()
    app.observability.health.register("force_fail", lambda: (False, "down"))
    port = app.observability.start_http(host="127.0.0.1", port=0)
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)
            assert False, "expected HTTPError 503"
        except urllib.error.HTTPError as exc:
            assert exc.code == 503
            body = json.loads(exc.read().decode("utf-8"))
            assert body["ok"] is False
            assert any(c["name"] == "force_fail" and c["ok"] is False for c in body["checks"])
    finally:
        app.observability.stop_http()
    print("[ok ] /healthz flips to 503 on failing check")


def scenario_structured_logger_emits_json_lines():
    print("[scenario] structured logger writes one JSON object per event")
    sink = io.StringIO()
    obs = Observability(log_stream=sink)
    obs.log("login.success", user_id="u_alice", device="dev_alice")
    obs.log("login.failure", reason="bad_password")
    lines = [ln for ln in sink.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["event"] == "login.success"
    assert parsed[0]["user_id"] == "u_alice"
    assert "ts" in parsed[0]
    assert parsed[1]["event"] == "login.failure"
    assert parsed[1]["reason"] == "bad_password"
    print("[ok ] both events parse as JSON with ts + event + extras")


def scenario_outcome_label_separates_ok_vs_error():
    print("[scenario] error response increments outcome=error counter")
    app = ServerApplication()
    # Bad password -> error response.
    app.dispatch({
        **make_envelope(MessageType.LOGIN_REQUEST, correlation_id="corr_bad", sequence=1),
        "payload": {"username": "alice", "password": "wrong", "device_id": "dev_x"},
    })
    text = app.observability.metrics.render_prometheus()
    # Prometheus exposition sorts labels alphabetically — outcome < type.
    assert 'outcome="error",type="login_request"' in text, text
    # Now do a success and confirm both labels coexist.
    _login(app, "alice", "alice_pw", "dev_alice", 2)
    text = app.observability.metrics.render_prometheus()
    assert 'outcome="ok",type="login_request"' in text, text
    print("[ok ] ok + error outcomes both counted separately")


def main() -> int:
    scenarios = [
        scenario_dispatch_emits_counter_and_histogram,
        scenario_metrics_endpoint_serves_prometheus,
        scenario_healthz_ok_when_all_checks_pass,
        scenario_healthz_failing_check_returns_503,
        scenario_structured_logger_emits_json_lines,
        scenario_outcome_label_separates_ok_vs_error,
    ]
    for s in scenarios:
        s()
    print(f"\nAll {len(scenarios)}/{len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
