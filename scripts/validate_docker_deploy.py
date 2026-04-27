"""Smoke test for a Docker-deployed telegram server."""
from __future__ import annotations

import argparse
import json
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--device", default="dev_docker_smoke")
    args = parser.parse_args()

    deadline = time.time() + 30
    while True:
        try:
            sock = socket.create_connection((args.host, args.port), timeout=2)
            break
        except OSError:
            if time.time() > deadline:
                print(f"[FAIL] Docker server did not open {args.host}:{args.port}")
                return 1
            time.sleep(0.5)

    request = {
        "type": "login_request",
        "correlation_id": "docker_smoke_login",
        "session_id": "",
        "actor_user_id": "",
        "sequence": 1,
        "payload": {
            "username": "alice",
            "password": "alice_pw",
            "device_id": args.device,
        },
    }
    sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
    line = sock.recv(65536).decode("utf-8")
    sock.close()

    response = json.loads(line)
    if response.get("type") != "login_response":
        print(f"[FAIL] unexpected response: {response}")
        return 1
    payload = response["payload"]
    print(f"docker deploy smoke ok: user={payload['user_id']} session={payload['session_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
