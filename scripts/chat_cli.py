"""Interactive two-party chat CLI against the telegram-like TCP server.

Usage:
    # 1. start the server in one terminal
    python -m server.main --tcp-server --port 8787

    # 2. in a second terminal, log in as alice
    python scripts/chat_cli.py --user alice --password alice_pw --device dev_alice_win

    # 3. in a third terminal, log in as bob
    python scripts/chat_cli.py --user bob --password bob_pw --device dev_bob_win

Type and press Enter to send a message to the default conv_alice_bob conversation.
Slash commands:
    /read <message_id>   mark message as read
    /edit <id> <text>    edit a message you sent
    /del <id>            soft-delete a message you sent
    /contacts            list your contacts
    /add <user_id>       add a contact
    /presence <uid>..    query online status
    /who                 list participants of the current conversation
    /sync                force a conversation sync (show history)
    /q                   quit
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path

# Allow running both as `python scripts/chat_cli.py` and `python -m scripts.chat_cli`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def send(sock: socket.socket, message: dict) -> None:
    sock.sendall((json.dumps(message) + "\n").encode("utf-8"))


def format_frame(frame: dict) -> str:
    ftype = frame.get("type", "?")
    payload = frame.get("payload") or {}
    if ftype == "message_deliver":
        sender = payload.get("sender_user_id", "?")
        text = payload.get("text", "")
        att = payload.get("attachment_id", "")
        mid = payload.get("message_id", "")
        tag = f" [attach={att}]" if att else ""
        return f"\r[{sender}] {text}{tag}  (msg={mid})"
    if ftype == "message_edited":
        return f"\r[edit by {payload.get('sender_user_id','?')}] msg={payload.get('message_id')} -> {payload.get('text')}"
    if ftype == "message_deleted":
        return f"\r[delete by {payload.get('sender_user_id','?')}] msg={payload.get('message_id')}"
    if ftype == "message_read_update":
        return f"\r[read] {payload.get('reader_user_id','?')} up to {payload.get('last_read_message_id')}"
    if ftype == "conversation_updated":
        pids = payload.get("participant_user_ids", [])
        return f"\r[conv {payload.get('conversation_id','?')} updated] participants={pids}"
    if ftype == "heartbeat_ack":
        return ""  # silent
    if ftype == "presence_query_response":
        rows = [
            f"  {u.get('user_id')}: {'online' if u.get('online') else 'offline'} (last_seen_at_ms={u.get('last_seen_at_ms')})"
            for u in payload.get("users", [])
        ]
        return "\r[presence]\n" + "\n".join(rows)
    if ftype == "contact_list_response":
        rows = [
            f"  {c.get('user_id')} ({c.get('display_name')}) - {'online' if c.get('online') else 'offline'}"
            for c in payload.get("contacts", [])
        ]
        return "\r[contacts]\n" + ("\n".join(rows) if rows else "  (empty)")
    if ftype == "conversation_sync":
        lines = ["\r[sync]"]
        for conv in payload.get("conversations", []):
            title = conv.get("title") or conv.get("conversation_id")
            lines.append(f"  {conv.get('conversation_id')} '{title}' {conv.get('participant_user_ids')}")
            for m in conv.get("messages", [])[-10:]:
                flags = []
                if m.get("edited"):
                    flags.append("edited")
                if m.get("deleted"):
                    flags.append("deleted")
                if m.get("attachment_id"):
                    flags.append(f"att={m.get('attachment_id')}")
                tag = f" ({','.join(flags)})" if flags else ""
                text = m.get("text", "")
                if m.get("deleted"):
                    text = "<deleted>"
                lines.append(f"    {m.get('message_id')} [{m.get('sender_user_id')}] {text}{tag}")
        return "\n".join(lines)
    if ftype == "error":
        return f"\r[ERR {payload.get('code','?')}] {payload.get('message','')}"
    # Fallback: raw JSON
    return f"\r[{ftype}] {json.dumps(payload, ensure_ascii=False)}"


class ChatClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port))
        self._file = self.sock.makefile("rb")
        self.session_id = ""
        self.user_id = ""
        self._seq = 0
        self._write_lock = threading.Lock()
        self._stop = False

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def send_locked(self, message: dict) -> None:
        with self._write_lock:
            send(self.sock, message)

    def read_loop(self, prompt: str) -> None:
        while not self._stop:
            try:
                line = self._file.readline()
            except Exception:
                return
            if not line:
                return
            try:
                frame = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            pretty = format_frame(frame)
            if not pretty:
                continue
            sys.stdout.write(pretty + "\n" + prompt)
            sys.stdout.flush()

    def login(self, username: str, password: str, device_id: str) -> None:
        self.send_locked(
            {
                "type": "login_request",
                "correlation_id": "login",
                "session_id": "",
                "actor_user_id": "",
                "sequence": self._next_seq(),
                "payload": {"username": username, "password": password, "device_id": device_id},
            }
        )
        line = self._file.readline()
        if not line:
            raise RuntimeError("server closed connection during login")
        resp = json.loads(line.decode("utf-8"))
        if resp.get("type") != "login_response":
            raise RuntimeError(f"login failed: {resp}")
        self.session_id = resp["payload"]["session_id"]
        self.user_id = resp["payload"]["user_id"]

    def envelope(self, msg_type: str, correlation_id: str, payload: dict) -> dict:
        return {
            "type": msg_type,
            "correlation_id": correlation_id,
            "session_id": self.session_id,
            "actor_user_id": self.user_id,
            "sequence": self._next_seq(),
            "payload": payload,
        }

    def heartbeat_loop(self, interval: float) -> None:
        while not self._stop:
            time.sleep(interval)
            if self._stop:
                return
            try:
                self.send_locked(self.envelope("heartbeat_ping", f"hb_{int(time.time())}", {"client_timestamp_ms": int(time.time() * 1000)}))
            except Exception:
                return

    def close(self) -> None:
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--conversation", default="conv_alice_bob")
    parser.add_argument("--heartbeat", type=float, default=10.0, help="seconds between heartbeats (0 = off)")
    args = parser.parse_args()

    client = ChatClient(args.host, args.port)
    client.login(args.user, args.password, args.device)
    print(f"logged in as {client.user_id} (session {client.session_id})")
    print(f"chatting in {args.conversation}. type '/q' to quit.")

    prompt = f"{client.user_id}> "

    reader = threading.Thread(target=client.read_loop, args=(prompt,), daemon=True)
    reader.start()

    if args.heartbeat > 0:
        heartbeat = threading.Thread(target=client.heartbeat_loop, args=(args.heartbeat,), daemon=True)
        heartbeat.start()

    # Initial sync so user sees history
    client.send_locked(client.envelope("conversation_sync", "initial_sync", {}))

    try:
        while True:
            line = input(prompt)
            line = line.strip()
            if not line:
                continue
            if line == "/q":
                break
            if line == "/sync":
                client.send_locked(client.envelope("conversation_sync", f"sync_{client._seq}", {}))
                continue
            if line == "/who":
                print(f"  conversation: {args.conversation}")
                continue
            if line == "/contacts":
                client.send_locked(client.envelope("contact_list_request", f"lst_{client._seq}", {}))
                continue
            if line.startswith("/add "):
                target = line[5:].strip()
                client.send_locked(client.envelope("contact_add", f"add_{client._seq}", {"target_user_id": target}))
                continue
            if line.startswith("/presence "):
                uids = line.split()[1:]
                client.send_locked(client.envelope("presence_query_request", f"prs_{client._seq}", {"user_ids": uids}))
                continue
            if line.startswith("/read "):
                mid = line.split(maxsplit=1)[1].strip()
                client.send_locked(client.envelope("message_read", f"rd_{client._seq}", {"conversation_id": args.conversation, "message_id": mid}))
                continue
            if line.startswith("/edit "):
                rest = line[6:].strip()
                parts = rest.split(maxsplit=1)
                if len(parts) != 2:
                    print("usage: /edit <message_id> <new text>")
                    continue
                mid, new_text = parts
                client.send_locked(client.envelope("message_edit", f"ed_{client._seq}", {"conversation_id": args.conversation, "message_id": mid, "text": new_text}))
                continue
            if line.startswith("/del "):
                mid = line[5:].strip()
                client.send_locked(client.envelope("message_delete", f"dl_{client._seq}", {"conversation_id": args.conversation, "message_id": mid}))
                continue
            # Default: send as a message
            client.send_locked(client.envelope("message_send", f"send_{client._seq}", {"conversation_id": args.conversation, "text": line}))
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
