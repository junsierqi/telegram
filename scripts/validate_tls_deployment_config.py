"""Static checks for the Docker TLS termination profile."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "deploy" / "docker" / "docker-compose.yml"
NGINX = ROOT / "deploy" / "tls" / "nginx.conf"
NGINX_POSTGRES = ROOT / "deploy" / "tls" / "nginx-postgres.conf"


def test_compose_has_tls_proxy_profile() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "telegram-tls-proxy:" in text
    assert "profiles:" in text
    assert "- tls" in text
    assert '"8443:8443"' in text
    assert "../tls/nginx.conf:/etc/nginx/nginx.conf:ro" in text
    assert "../tls/certs:/etc/nginx/certs:ro" in text


def test_compose_has_postgres_tls_proxy_profile() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "telegram-tls-proxy-postgres:" in text
    assert "telegram-server-postgres" in text
    assert '"8444:8443"' in text
    assert "../tls/nginx-postgres.conf:/etc/nginx/nginx.conf:ro" in text
    assert "../tls/certs:/etc/nginx/certs:ro" in text


def test_nginx_terminates_tls_to_control_plane() -> None:
    text = NGINX.read_text(encoding="utf-8")
    assert "stream {" in text
    assert "listen 8443 ssl;" in text
    assert "ssl_certificate /etc/nginx/certs/server.crt;" in text
    assert "ssl_certificate_key /etc/nginx/certs/server.key;" in text
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in text
    assert "server telegram-server:8787;" in text
    assert "proxy_pass telegram_control_plane;" in text


def test_postgres_nginx_terminates_tls_to_postgres_control_plane() -> None:
    text = NGINX_POSTGRES.read_text(encoding="utf-8")
    assert "stream {" in text
    assert "listen 8443 ssl;" in text
    assert "ssl_certificate /etc/nginx/certs/server.crt;" in text
    assert "ssl_certificate_key /etc/nginx/certs/server.key;" in text
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in text
    assert "server telegram-server-postgres:8787;" in text
    assert "proxy_pass telegram_control_plane;" in text


SCENARIOS = [
    ("compose_has_tls_proxy_profile", test_compose_has_tls_proxy_profile),
    ("compose_has_postgres_tls_proxy_profile", test_compose_has_postgres_tls_proxy_profile),
    ("nginx_terminates_tls_to_control_plane", test_nginx_terminates_tls_to_control_plane),
    (
        "postgres_nginx_terminates_tls_to_postgres_control_plane",
        test_postgres_nginx_terminates_tls_to_postgres_control_plane,
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, fn in SCENARIOS:
        try:
            fn()
            print(f"[ok ] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
    print(f"passed {len(SCENARIOS) - len(failures)}/{len(SCENARIOS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
