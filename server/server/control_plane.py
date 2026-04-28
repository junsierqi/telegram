from __future__ import annotations

import json
import socketserver
import ssl
import threading
from typing import Any

from .app import ServerApplication
from .protocol import ErrorCode, ErrorResponsePayload, MessageType, make_response


class _ControlPlaneHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        app: ServerApplication = self.server.app  # type: ignore[attr-defined]

        write_lock = threading.Lock()

        def writer(envelope: dict[str, Any]) -> None:
            with write_lock:
                # ensure_ascii=False keeps non-ASCII characters as UTF-8 on the wire
                # instead of \uXXXX escapes — smaller frames and matches what every
                # current client (incl. C++ json_value.cpp) decodes natively.
                self.wfile.write(
                    (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8")
                )
                self.wfile.flush()

        registered_session_id: str | None = None

        try:
            while True:
                raw_line = self.rfile.readline()
                if not raw_line:
                    return

                try:
                    message = json.loads(raw_line.decode("utf-8"))
                    response = app.dispatch(message)
                except Exception as exc:  # pragma: no cover - debug path
                    response = make_response(
                        MessageType.ERROR,
                        correlation_id="corr_transport_error",
                        payload=ErrorResponsePayload(
                            code=ErrorCode.UNKNOWN.value,
                            message=str(exc),
                        ),
                    ).to_dict()

                if (
                    registered_session_id is None
                    and response.get("type") == MessageType.LOGIN_RESPONSE.value
                ):
                    payload = response.get("payload") or {}
                    session_id = payload.get("session_id")
                    if session_id:
                        app.connection_registry.register(session_id, writer)
                        registered_session_id = session_id

                writer(response)
        finally:
            if registered_session_id is not None:
                app.connection_registry.unregister(registered_session_id)


class ThreadedControlPlaneServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        app: ServerApplication,
        *,
        tls_cert_file: str | None = None,
        tls_key_file: str | None = None,
    ) -> None:
        if bool(tls_cert_file) != bool(tls_key_file):
            raise ValueError("tls_cert_file and tls_key_file must be configured together")
        context: ssl.SSLContext | None = None
        if tls_cert_file and tls_key_file:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=tls_cert_file, keyfile=tls_key_file)
        super().__init__(server_address, _ControlPlaneHandler)
        self.app = app
        self._ssl_context = context
        self.tls_enabled = context is not None

    def get_request(self) -> tuple[Any, Any]:
        sock, addr = super().get_request()
        if self._ssl_context is None:
            return sock, addr
        return self._ssl_context.wrap_socket(sock, server_side=True), addr


def serve_tcp(
    host: str,
    port: int,
    state_file: str | None = None,
    *,
    app: ServerApplication | None = None,
    db_file: str | None = None,
    pg_dsn: str | None = None,
    attachment_dir: str | None = None,
    tls_cert_file: str | None = None,
    tls_key_file: str | None = None,
) -> None:
    if app is None:
        app = ServerApplication(
            state_file=state_file,
            db_file=db_file,
            pg_dsn=pg_dsn,
            attachment_dir=attachment_dir,
        )
    print("[server] control plane starting")
    print(f"[server] listening on {host}:{port}")
    print(f"[server] tls={'enabled' if tls_cert_file else 'disabled'}")
    print(f"[server] {app.auth_service.describe()}")
    print(f"[server] {app.chat_service.describe()}")
    print(f"[server] {app.presence_service.describe()}")
    print(f"[server] {app.remote_session_service.describe()}")

    with ThreadedControlPlaneServer(
        (host, port),
        app,
        tls_cert_file=tls_cert_file,
        tls_key_file=tls_key_file,
    ) as server:
        server.serve_forever()
