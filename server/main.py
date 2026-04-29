from __future__ import annotations

import argparse
import os
from pathlib import Path

from .server.app import create_app
from .server.control_plane import serve_tcp
from .server.media_plane import serve_udp_in_thread
from .server.screen_source import make_test_pattern_source
from .server.state import InMemoryState
from .server.web_bridge import serve_web_bridge_in_thread


_ACTIVE_REMOTE_STATES = {"approved", "negotiating", "connecting", "streaming", "controlling"}
# M109: voice/video calls in 'accepted' state authorize their participants
# on the media plane the same way remote-control sessions do.
_ACTIVE_CALL_STATES = {"accepted"}


def _build_session_authorizer(state: InMemoryState):
    """session_id is authorized when it points at a logged-in user who
    is currently a participant in at least one active (post-approval,
    pre-terminal) remote session OR an accepted voice/video call.
    Being only logged-in is not enough — the media plane only carries
    traffic tied to an approved remote session or an accepted call.
    """

    def authorize(session_id: str) -> bool:
        record = state.sessions.get(session_id)
        if record is None:
            return False
        for remote in state.remote_sessions.values():
            if remote.state not in _ACTIVE_REMOTE_STATES:
                continue
            if record.user_id in (remote.requester_user_id, remote.target_user_id):
                return True
        for call in state.calls.values():
            if call.state not in _ACTIVE_CALL_STATES:
                continue
            if record.user_id in (call.caller_user_id, call.callee_user_id):
                return True
        return False

    return authorize


def main() -> None:
    parser = argparse.ArgumentParser(description="telegram_like server entry point")
    parser.add_argument(
        "--tcp-server",
        action="store_true",
        help="run the line-delimited JSON TCP control plane server",
    )
    parser.add_argument("--host", default=os.getenv("TELEGRAM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("TELEGRAM_PORT", "8787")))
    parser.add_argument(
        "--state-file",
        default=os.getenv(
            "TELEGRAM_STATE_FILE",
            str(Path(__file__).resolve().parent / "data" / "runtime_state.json"),
        ),
        help="path to the JSON runtime state file used for lightweight persistence",
    )
    parser.add_argument(
        "--db-file",
        default=os.getenv("TELEGRAM_DB_FILE", ""),
        help="Optional SQLite durable state database. When set, it supersedes --state-file.",
    )
    parser.add_argument(
        "--pg-dsn",
        default=os.getenv("TELEGRAM_PG_DSN", ""),
        help=(
            "Optional PostgreSQL DSN for the first repository-backed persistence path. "
            "When set, it supersedes --db-file and --state-file."
        ),
    )
    parser.add_argument(
        "--attachment-dir",
        default=os.getenv("TELEGRAM_ATTACHMENT_DIR", ""),
        help=(
            "Directory for attachment blob content. Empty = '<state-file>.attachments'. "
            "Metadata stays in the runtime state JSON."
        ),
    )
    parser.add_argument(
        "--session-ttl-seconds",
        type=float,
        default=float(os.getenv("TELEGRAM_SESSION_TTL_SECONDS", "0")),
        help="Optional login session max age in seconds. 0 disables expiry.",
    )
    parser.add_argument(
        "--tls-cert-file",
        default=os.getenv("TELEGRAM_TLS_CERT_FILE", ""),
        help="Optional PEM certificate file for native TLS on the TCP control plane.",
    )
    parser.add_argument(
        "--tls-key-file",
        default=os.getenv("TELEGRAM_TLS_KEY_FILE", ""),
        help="Optional PEM private key file for native TLS on the TCP control plane.",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=int(os.getenv("TELEGRAM_UDP_PORT", "0")),
        help="Optional UDP media-plane echo port. 0 = disabled.",
    )
    parser.add_argument(
        "--screen-source",
        default="",
        help=(
            "Optional test-pattern source for the UDP frame stream. "
            "Format: '<pattern>[:<width>x<height>]' e.g. 'gradient:24x16'. "
            "Empty = legacy _fake_frame_payload."
        ),
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=int(os.getenv("TELEGRAM_WEB_PORT", "0")),
        help=(
            "Optional HTTP + WebSocket bridge port for the browser client (M110). "
            "0 = disabled. Serves server/web/index.html + app.js at / and exposes "
            "the same dispatch surface as --tcp-server over a WS upgrade at /ws."
        ),
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=int(os.getenv("TELEGRAM_METRICS_PORT", "0")),
        help=(
            "Optional sidecar /metrics + /healthz HTTP port (M92 observability). "
            "0 = disabled. Bind 0.0.0.0 so Prometheus scrapers in another "
            "container can reach it; use 127.0.0.1 if scraped locally."
        ),
    )
    parser.add_argument(
        "--metrics-host",
        default=os.getenv("TELEGRAM_METRICS_HOST", "127.0.0.1"),
        help="Bind address for --metrics-port (default 127.0.0.1; set 0.0.0.0 for cross-container scraping).",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("TELEGRAM_REDIS_URL", ""),
        help=(
            "Optional Redis REST gateway endpoint (M111+M116). When set with "
            "--redis-token, PresenceService reads/writes a hot-state cache "
            "before scanning the in-memory sessions table."
        ),
    )
    parser.add_argument(
        "--redis-token",
        default=os.getenv("TELEGRAM_REDIS_TOKEN", ""),
        help="Bearer token for the Redis REST gateway (PA-011).",
    )
    parser.add_argument(
        "--redis-fake",
        action="store_true",
        help=(
            "Bind an in-memory FakeRedisTransport instead of Redis. Useful "
            "for single-process dev to exercise the cache code path; not "
            "useful in multi-replica production (each replica gets its own)."
        ),
    )
    args = parser.parse_args()

    persistence_anchor = args.db_file or args.state_file
    attachment_dir = args.attachment_dir or f"{persistence_anchor}.attachments"

    # M116: build the optional Redis hot-state cache before app construction
    # so PresenceService picks it up at __init__.
    redis_cache = None
    if args.redis_url:
        from .server.redis_cache import RedisCacheBridge, RedisHttpTransport
        transport = RedisHttpTransport(
            endpoint_url=args.redis_url,
            token=args.redis_token,
            dry_run=False,
        )
        redis_cache = RedisCacheBridge(transport)
        print(f"[server] Redis cache wired to {args.redis_url}")
    elif args.redis_fake:
        from .server.redis_cache import RedisCacheBridge
        redis_cache = RedisCacheBridge()  # FakeRedisTransport default
        print("[server] Redis cache wired to in-memory FakeRedisTransport (dev only)")

    app = create_app(
        state_file=None if (args.pg_dsn or args.db_file) else args.state_file,
        db_file=None if args.pg_dsn else (args.db_file or None),
        pg_dsn=args.pg_dsn or None,
        attachment_dir=attachment_dir,
        session_ttl_seconds=args.session_ttl_seconds,
        redis_cache=redis_cache,
    )

    screen_source = None
    if args.screen_source:
        pattern, _, dims = args.screen_source.partition(":")
        width, height = 24, 16
        if dims:
            w_str, _, h_str = dims.partition("x")
            if w_str and h_str:
                width, height = int(w_str), int(h_str)
        screen_source = make_test_pattern_source(width=width, height=height, pattern=pattern or "gradient")

    if args.udp_port:
        serve_udp_in_thread(
            args.host,
            args.udp_port,
            authorizer=_build_session_authorizer(app.state),
            screen_source=screen_source,
        )

    if args.web_port:
        serve_web_bridge_in_thread(args.host, args.web_port, app)
        print(f"[server] web bridge listening on http://{args.host}:{args.web_port}/")

    if args.metrics_port:
        bound = app.observability.start_http(host=args.metrics_host, port=args.metrics_port)
        print(f"[server] /metrics + /healthz on http://{args.metrics_host}:{bound}/")

    if args.tcp_server:
        serve_tcp(
            args.host,
            args.port,
            state_file=args.state_file,
            app=app,
            db_file=None if args.pg_dsn else (args.db_file or None),
            pg_dsn=args.pg_dsn or None,
            attachment_dir=attachment_dir,
            tls_cert_file=args.tls_cert_file or None,
            tls_key_file=args.tls_key_file or None,
        )
        return

    # If only sidecar threads (--web-port / --metrics-port) are set without
    # --tcp-server, block on the main thread so the process stays alive.
    if args.web_port or args.metrics_port:
        import threading
        threading.Event().wait()
        return

    app.run()


if __name__ == "__main__":
    main()
