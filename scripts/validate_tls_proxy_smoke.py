"""Smoke test for a TLS-terminating proxy in front of the telegram server."""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--server-name", default="localhost")
    parser.add_argument("--cafile", default="deploy/tls/certs/server.crt")
    parser.add_argument("--device", default="dev_tls_proxy_smoke")
    args = parser.parse_args()

    deadline = time.time() + 45
    context = ssl.create_default_context(cafile=args.cafile)
    last_error: Exception | None = None
    while True:
        try:
            raw = socket.create_connection((args.host, args.port), timeout=3)
            sock = context.wrap_socket(raw, server_hostname=args.server_name)
            break
        except Exception as exc:
            last_error = exc
            if time.time() > deadline:
                print(f"[FAIL] TLS proxy did not open {args.host}:{args.port}: {last_error}")
                return 1
            time.sleep(0.5)

    request = {
        "type": "login_request",
        "correlation_id": "tls_proxy_smoke_login",
        "session_id": "",
        "actor_user_id": "",
        "sequence": 1,
        "payload": {
            "username": "alice",
            "password": "alice_pw",
            "device_id": args.device,
        },
    }
    with sock:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        response = json.loads(sock.recv(65536).decode("utf-8"))

    if response.get("type") != "login_response":
        print(f"[FAIL] unexpected response: {response}")
        return 1
    payload = response["payload"]
    print(f"tls proxy smoke ok: user={payload['user_id']} session={payload['session_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
