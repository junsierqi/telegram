"""Observability primitives (M92): structured logger + Prometheus exposition
+ a tiny stdlib-only sidecar HTTP server for /metrics + /healthz.

Stays stdlib-only (`json`, `time`, `http.server`, `threading`) so the
deployment story matches the rest of the codebase.

Usage:

    obs = Observability()                       # default stderr logger
    obs.metrics.inc("messages_sent_total")      # bump a counter
    obs.metrics.inc("messages_sent_total",
                    labels={"conversation": "conv_alice_bob"})
    obs.start_http(port=9100)                   # exposes /metrics + /healthz
    obs.log("login.success", user_id="u_alice") # JSON line on stderr

The HTTP server runs on its own thread so the main TCP control plane is
never blocked by a /metrics scrape.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


_LABEL_VALUE_ESCAPES = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n"})


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = []
    for k in sorted(labels):
        v = str(labels[k]).translate(_LABEL_VALUE_ESCAPES)
        parts.append(f'{k}="{v}"')
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    """Counters + gauges + a small histogram primitive.

    Histograms track count + sum + bucketed counts so the Prometheus
    exposition follows the standard pattern. Buckets are configurable per
    metric; defaults are a coarse latency-friendly set.
    """

    DEFAULT_BUCKETS = (0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        # histogram name -> (buckets, dict[label_key -> {bucket_le -> count, "sum", "count"}])
        self._histograms: dict[str, tuple[tuple[float, ...], dict[tuple[tuple[str, str], ...], dict[str, float]]]] = {}
        # name -> human-readable description
        self._descriptions: dict[str, str] = {}

    def describe(self, name: str, help_text: str) -> None:
        self._descriptions[name] = help_text

    @staticmethod
    def _label_key(labels: Optional[dict[str, str]]) -> tuple[tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((k, str(v)) for k, v in labels.items()))

    def inc(self, name: str, value: float = 1.0,
            labels: Optional[dict[str, str]] = None) -> None:
        key = (name, self._label_key(labels))
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float,
                  labels: Optional[dict[str, str]] = None) -> None:
        key = (name, self._label_key(labels))
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float,
                labels: Optional[dict[str, str]] = None,
                buckets: Optional[tuple[float, ...]] = None) -> None:
        with self._lock:
            entry = self._histograms.get(name)
            if entry is None:
                entry = (buckets or self.DEFAULT_BUCKETS, {})
                self._histograms[name] = entry
            buckets_used, by_label = entry
            label_key = self._label_key(labels)
            row = by_label.setdefault(label_key, {"sum": 0.0, "count": 0.0})
            row["sum"] += value
            row["count"] += 1
            for b in buckets_used:
                if value <= b:
                    bk = f"le_{b}"
                    row[bk] = row.get(bk, 0.0) + 1
            row["le_+Inf"] = row.get("le_+Inf", 0.0) + 1

    def render_prometheus(self) -> str:
        out: list[str] = []
        # Counters
        names_emitted: set[str] = set()
        with self._lock:
            counter_groups: dict[str, list[tuple[tuple[tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, label_key), value in self._counters.items():
                counter_groups[name].append((label_key, value))
            for name in sorted(counter_groups):
                if name in self._descriptions:
                    out.append(f"# HELP {name} {self._descriptions[name]}")
                out.append(f"# TYPE {name} counter")
                for label_key, value in sorted(counter_groups[name]):
                    out.append(f"{name}{_format_labels(dict(label_key))} {value}")
                names_emitted.add(name)
            gauge_groups: dict[str, list[tuple[tuple[tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, label_key), value in self._gauges.items():
                gauge_groups[name].append((label_key, value))
            for name in sorted(gauge_groups):
                if name in self._descriptions:
                    out.append(f"# HELP {name} {self._descriptions[name]}")
                out.append(f"# TYPE {name} gauge")
                for label_key, value in sorted(gauge_groups[name]):
                    out.append(f"{name}{_format_labels(dict(label_key))} {value}")
                names_emitted.add(name)
            for name, (buckets, by_label) in sorted(self._histograms.items()):
                if name in self._descriptions:
                    out.append(f"# HELP {name} {self._descriptions[name]}")
                out.append(f"# TYPE {name} histogram")
                for label_key in sorted(by_label):
                    row = by_label[label_key]
                    base_labels = dict(label_key)
                    for b in buckets:
                        labels_with_le = dict(base_labels, le=str(b))
                        out.append(f"{name}_bucket{_format_labels(labels_with_le)} {row.get(f'le_{b}', 0.0)}")
                    labels_inf = dict(base_labels, le="+Inf")
                    out.append(f"{name}_bucket{_format_labels(labels_inf)} {row.get('le_+Inf', 0.0)}")
                    out.append(f"{name}_sum{_format_labels(base_labels)} {row['sum']}")
                    out.append(f"{name}_count{_format_labels(base_labels)} {row['count']}")
        return "\n".join(out) + "\n"


class StructuredLogger:
    """Emit JSON lines, one per event. Configurable stream so tests can
    capture into io.StringIO; production uses stderr."""

    def __init__(self, stream=None, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._clock = clock or time.time
        self._lock = threading.Lock()

    def log(self, event: str, **fields) -> None:
        record = {
            "ts": int(self._clock() * 1000),
            "event": event,
        }
        record.update(fields)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


@dataclass
class HealthCheck:
    name: str
    fn: Callable[[], tuple[bool, str]]


class HealthAggregator:
    """Each registered HealthCheck.fn() returns (ok, detail). /healthz
    returns 200 only if every check is ok; otherwise 503 + the detail."""

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = []

    def register(self, name: str, fn: Callable[[], tuple[bool, str]]) -> None:
        self._checks.append(HealthCheck(name=name, fn=fn))

    def evaluate(self) -> tuple[bool, list[tuple[str, bool, str]]]:
        results: list[tuple[str, bool, str]] = []
        all_ok = True
        for check in self._checks:
            try:
                ok, detail = check.fn()
            except Exception as exc:  # pragma: no cover
                ok, detail = False, f"check raised: {exc}"
            results.append((check.name, ok, detail))
            if not ok:
                all_ok = False
        return all_ok, results


class _ObservabilityHandler(BaseHTTPRequestHandler):
    """Sidecar HTTP handler for /metrics + /healthz."""

    # quiet the default 127.0.0.1 access log noise
    def log_message(self, fmt, *args):  # noqa: D401
        return

    def do_GET(self):  # noqa: N802
        observability: Observability = self.server.observability  # type: ignore[attr-defined]
        if self.path == "/metrics":
            body = observability.metrics.render_prometheus().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/healthz":
            ok, results = observability.health.evaluate()
            payload = {
                "ok": ok,
                "checks": [{"name": n, "ok": k, "detail": d} for n, k, d in results],
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


class Observability:
    def __init__(
        self,
        *,
        log_stream=None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.metrics = MetricsRegistry()
        self.logger = StructuredLogger(stream=log_stream, clock=clock)
        self.health = HealthAggregator()
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._declare_default_metrics()

    def _declare_default_metrics(self) -> None:
        self.metrics.describe("dispatch_requests_total",
                              "Inbound control-plane request count by message type and outcome.")
        self.metrics.describe("dispatch_request_duration_seconds",
                              "Latency of dispatch() per message type.")
        self.metrics.describe("messages_sent_total",
                              "Successful MESSAGE_SEND completions.")
        self.metrics.describe("attachments_uploaded_total",
                              "Successful chunked + small-file attachment finalizations.")
        self.metrics.describe("phone_otp_requests_total",
                              "Phone OTP request_code invocations.")
        self.metrics.describe("phone_otp_verifications_total",
                              "Phone OTP verify_code invocations by outcome.")
        self.metrics.describe("rate_limited_total",
                              "Requests rejected by the rate limiter.")
        self.metrics.describe("active_sessions",
                              "Currently registered live sessions in the connection registry.")

    def log(self, event: str, **fields) -> None:
        self.logger.log(event, **fields)

    def start_http(self, *, host: str = "127.0.0.1", port: int = 9100) -> int:
        """Start the sidecar /metrics + /healthz server. Returns the bound port
        (use 0 to let the OS pick — useful for tests)."""
        server = ThreadingHTTPServer((host, port), _ObservabilityHandler)
        server.observability = self  # type: ignore[attr-defined]
        bound_port = server.server_address[1]
        self._http_server = server
        self._http_thread = threading.Thread(
            target=server.serve_forever, name="observability-http", daemon=True,
        )
        self._http_thread.start()
        return bound_port

    def stop_http(self) -> None:
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
            self._http_thread = None

    def describe(self) -> str:
        return "observability — structured logger + prometheus metrics + health probe"
