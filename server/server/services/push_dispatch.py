"""Push delivery worker that drains PushTokenService.pending_deliveries.

This is the bridge between the in-memory mock queue from M84 and a real
Firebase Cloud Messaging / Apple Push Notification Service transport.

Pluggable shape so:

  * tests use FakeTransport (records calls in a list).
  * default servers use LogOnlyTransport (writes to stderr/log) — no
    credentials required.
  * production wires FCMHttpTransport once a service account JSON is
    available (see PA-008 in 08-atlas-task-library.md). The HTTP call is
    intentionally stubbed in dry_run mode by default so CI can exercise the
    code path without ever hitting Google's servers.

Worker contract:

    worker = PushDispatchWorker(token_service, transport_for=lambda p: ...)
    delivered = worker.tick()  # returns DeliveryReport(successful, failed)

A real deployment runs `tick()` from a background thread on a short cadence
(every 1-5 s). Tests just call it synchronously between operations.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from .push_tokens import PendingDelivery, PushTokenService


@dataclass
class DeliveryAttempt:
    delivery: PendingDelivery
    transport: str
    success: bool
    detail: str = ""


@dataclass
class DeliveryReport:
    successful: list[DeliveryAttempt] = field(default_factory=list)
    failed: list[DeliveryAttempt] = field(default_factory=list)

    def total(self) -> int:
        return len(self.successful) + len(self.failed)


class Transport(Protocol):
    """Subclass / duck-type to add a real wire transport.
    `name` matches the platform string a client registered with — "fcm",
    "apns", "wns", "mock", etc.
    """
    name: str

    def send(self, deliveries: list[PendingDelivery]) -> list[DeliveryAttempt]:
        ...  # pragma: no cover


class FakeTransport:
    """Records every dispatched batch in `received` for tests to assert on."""
    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.received: list[PendingDelivery] = []

    def send(self, deliveries: list[PendingDelivery]) -> list[DeliveryAttempt]:
        self.received.extend(deliveries)
        return [
            DeliveryAttempt(delivery=d, transport=self.name, success=True,
                            detail="fake-ok")
            for d in deliveries
        ]


class LogOnlyTransport:
    """Default transport: just writes a one-line summary per delivery to a
    configurable stream. Safe to wire in any environment — no credentials,
    no network access required.
    """
    def __init__(self, name: str, stream=None) -> None:
        self.name = name
        self._stream = stream if stream is not None else sys.stderr

    def send(self, deliveries: list[PendingDelivery]) -> list[DeliveryAttempt]:
        attempts: list[DeliveryAttempt] = []
        for d in deliveries:
            self._stream.write(
                f"[push:{self.name}] -> user={d.user_id} device={d.device_id} "
                f"kind={d.kind} body={d.body_summary!r}\n"
            )
            attempts.append(DeliveryAttempt(
                delivery=d, transport=self.name, success=True,
                detail="logged",
            ))
        return attempts


class FCMHttpTransport:
    """FCM v1 HTTP transport skeleton.

    - With `dry_run=True` (default) it builds the request payload but does
      NOT post anywhere. Used by CI/validators to exercise the wiring
      without an FCM project.
    - With `dry_run=False` and a `bearer_token` (obtained out-of-band from
      a service account JSON via google-auth or an equivalent), it POSTs
      to https://fcm.googleapis.com/v1/projects/<project_id>/messages:send.

    Acquiring the bearer token + project_id is PA-008 — that's where a
    service account JSON file plus the google.oauth2.service_account flow
    enters the picture.
    """
    def __init__(
        self,
        *,
        project_id: str = "",
        bearer_token: str = "",
        dry_run: bool = True,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.name = "fcm"
        self.project_id = project_id
        self.bearer_token = bearer_token
        self.dry_run = dry_run or not (project_id and bearer_token)
        self.timeout_seconds = timeout_seconds
        # Tests can read this list to inspect what would have been POSTed.
        self.dry_run_payloads: list[dict] = []

    def send(self, deliveries: list[PendingDelivery]) -> list[DeliveryAttempt]:
        attempts: list[DeliveryAttempt] = []
        for d in deliveries:
            payload = {
                "message": {
                    "token": d.token,
                    "notification": {
                        "title": "Telegram-like",
                        "body": d.body_summary or d.kind,
                    },
                    "data": {"kind": d.kind, "user_id": d.user_id},
                }
            }
            if self.dry_run:
                self.dry_run_payloads.append(payload)
                attempts.append(DeliveryAttempt(
                    delivery=d, transport=self.name, success=True,
                    detail="dry_run",
                ))
                continue
            url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "Content-Type": "application/json; UTF-8",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    code = resp.getcode()
                if 200 <= code < 300:
                    attempts.append(DeliveryAttempt(
                        delivery=d, transport=self.name, success=True,
                        detail=f"http_{code}",
                    ))
                else:
                    attempts.append(DeliveryAttempt(
                        delivery=d, transport=self.name, success=False,
                        detail=f"http_{code}",
                    ))
            except Exception as exc:  # network or auth error
                attempts.append(DeliveryAttempt(
                    delivery=d, transport=self.name, success=False,
                    detail=f"transport_error:{type(exc).__name__}",
                ))
        return attempts


class PushDispatchWorker:
    def __init__(
        self,
        token_service: PushTokenService,
        *,
        transport_for: Optional[Callable[[str], Transport | None]] = None,
        default_transport: Optional[Transport] = None,
    ) -> None:
        self._tokens = token_service
        self._transport_for = transport_for
        # Used when the platform has no specific transport registered.
        self._default = default_transport or LogOnlyTransport("log-fallback")

    def tick(self) -> DeliveryReport:
        """Drain the queue and dispatch one batch per platform.

        Returns DeliveryReport with successful/failed splits so callers
        (or tests) can act on the outcome — e.g., a real prod worker
        could re-enqueue failed deliveries for retry.
        """
        report = DeliveryReport()
        pending = self._tokens.drain_pending()
        if not pending:
            return report
        # Group by platform for efficient batching.
        by_platform: dict[str, list[PendingDelivery]] = {}
        for d in pending:
            by_platform.setdefault(d.platform, []).append(d)
        for platform, batch in by_platform.items():
            transport = None
            if self._transport_for is not None:
                transport = self._transport_for(platform)
            if transport is None:
                transport = self._default
            attempts = transport.send(batch)
            for a in attempts:
                if a.success:
                    report.successful.append(a)
                else:
                    report.failed.append(a)
        return report

    def describe(self) -> str:
        return "push dispatch worker — pluggable transports, drains PushTokenService queue"
