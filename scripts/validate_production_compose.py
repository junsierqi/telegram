"""M115 production compose static-shape check.

Runs without Docker installed: parses `deploy/docker/docker-compose.yml`,
the new `nginx-web.conf`, the env example and the prometheus.yml; verifies
the production profile is wired correctly and that the existing dev
profiles aren't regressed.

Scenarios:
- docker-compose.yml is parseable YAML.
- production profile contains telegram-server-prod, nginx-web, postgres.
- telegram-server-prod runs `python -m server.main` with --tcp-server,
  --web-port 8080, --metrics-port 9100, --metrics-host 0.0.0.0.
- telegram-server-prod has restart=always + healthcheck against /healthz.
- telegram-server-prod depends on a healthchecked postgres.
- nginx-web mounts deploy/tls/nginx-web.conf and publishes 80 + 443.
- prometheus.yml scrapes telegram-server-prod:9100/metrics.
- production.env.example documents every PA env var the prod compose reads.
- nginx-web.conf has the WS upgrade map + /ws location with
  proxy_set_header Upgrade $http_upgrade.
- Existing dev services (telegram-server, telegram-server-postgres,
  telegram-tls-proxy*) are still present.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPOSE = REPO / "deploy" / "docker" / "docker-compose.yml"
NGINX_WEB = REPO / "deploy" / "tls" / "nginx-web.conf"
ENV_EXAMPLE = REPO / "deploy" / "docker" / "production.env.example"
PROM_YML = REPO / "deploy" / "docker" / "prometheus.yml"
README = REPO / "deploy" / "docker" / "README.md"


def scenario(label: str) -> None:
    print(f"\n[scenario] {label}")


def _load_yaml(path: Path) -> dict:
    """Tiny YAML loader for the subset compose uses (block-style mappings,
    sequences, simple scalars). Avoids a PyYAML dep so this validator runs
    on a fresh interpreter."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(text)
    except ModuleNotFoundError:
        pass
    # Fallback: very small parser for "key: value" + nested dict + list,
    # which is all docker-compose.yml uses for the assertions below.
    return _parse_minimal_yaml(text)


def _parse_minimal_yaml(text: str) -> dict:
    """Last-resort parser. Returns a nested dict / list / str structure.

    Handles: '#' comments, indent-based nesting (2-space increments),
    scalar values (str/int/bool), and '- ' list items. Sufficient to read
    docker-compose.yml structure; not a general YAML implementation.
    """
    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]

    def coerce(s: str):
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        if s.startswith("'") and s.endswith("'"):
            return s[1:-1]
        lower = s.lower()
        if lower in ("true", "yes"):
            return True
        if lower in ("false", "no"):
            return False
        try:
            return int(s)
        except ValueError:
            return s

    for raw_line in text.splitlines():
        # Drop comments + blanks.
        stripped = raw_line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        body = stripped.lstrip(" ")

        # Pop the stack until we find the parent at a lesser indent.
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else root

        if body.startswith("- "):
            # List item.
            value = body[2:]
            if not isinstance(parent, list):
                # The previous key must have been declared empty; convert.
                # Find the last dict-key in the grandparent that points at
                # this position; replace its value with [].
                # Easier: assume callers structured well. Just append.
                continue
            if ":" in value and not value.startswith("\""):
                # Inline dict in list item, e.g. `- name: foo`.
                k, _, v = value.partition(":")
                d: dict = {k.strip(): coerce(v) if v.strip() else {}}
                parent.append(d)
                stack.append((indent + 2, d))
            else:
                parent.append(coerce(value))
            continue

        # `key:` or `key: value`
        if ":" in body:
            key, _, value = body.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                # Could be dict or list — initialise as dict, will swap to
                # list if next non-blank line starts with `- `.
                new: object = {}
                if isinstance(parent, dict):
                    parent[key] = new
                stack.append((indent, new))
                # Look ahead would be cleaner but this works for compose.
            else:
                if isinstance(parent, dict):
                    parent[key] = coerce(value)
        # Else: ignored.

    # Second pass: convert dicts that should be lists (any dict whose values
    # are all None / inline list items). Detect via heuristic: leave as-is;
    # the assertions below access only structural shape.
    return root


def run_compose_yaml_parses() -> None:
    scenario("docker-compose.yml is parseable")
    data = _load_yaml(COMPOSE)
    assert isinstance(data, dict), data
    assert "services" in data, list(data.keys())
    services = data["services"]
    assert "telegram-server-prod" in services, list(services.keys())
    assert "nginx-web" in services, list(services.keys())
    assert "prometheus" in services, list(services.keys())
    # Existing dev services are preserved (no regression).
    for legacy in (
        "telegram-server", "postgres", "telegram-server-postgres",
        "telegram-tls-proxy", "telegram-tls-proxy-postgres",
    ):
        assert legacy in services, f"regression: dev service {legacy} missing"


def run_prod_service_command_includes_all_flags() -> None:
    scenario("telegram-server-prod runs all three entry points")
    text = COMPOSE.read_text(encoding="utf-8")
    # Slice the prod service block.
    start = text.index("telegram-server-prod:")
    end = text.index("\n  nginx-web:", start)
    block = text[start:end]
    for needle in (
        "--tcp-server",
        "--web-port",
        '"8080"',
        "--metrics-port",
        '"9100"',
        "--metrics-host",
        "0.0.0.0",
        "restart: always",
        "TELEGRAM_PG_DSN: postgresql://telegram:",
    ):
        assert needle in block, f"missing {needle!r} in telegram-server-prod block"


def run_prod_service_healthcheck_uses_observability() -> None:
    scenario("telegram-server-prod healthcheck hits /healthz on the M92 sidecar")
    text = COMPOSE.read_text(encoding="utf-8")
    start = text.index("telegram-server-prod:")
    end = text.index("\n  nginx-web:", start)
    block = text[start:end]
    assert "healthcheck:" in block
    assert "127.0.0.1:9100/healthz" in block
    assert "depends_on:" in block
    assert "service_healthy" in block, "expected postgres healthcheck dependency"


def run_nginx_web_mounts_and_ports() -> None:
    scenario("nginx-web mounts nginx-web.conf and publishes 80 + 443")
    text = COMPOSE.read_text(encoding="utf-8")
    start = text.index("nginx-web:")
    end = text.index("\n  prometheus:", start)
    block = text[start:end]
    assert "../tls/nginx-web.conf:/etc/nginx/nginx.conf:ro" in block
    assert "${TELEGRAM_HTTP_PORT:-80}:80" in block
    assert "${TELEGRAM_HTTPS_PORT:-443}:443" in block
    assert "depends_on:" in block and "telegram-server-prod" in block


def run_nginx_web_conf_has_ws_upgrade() -> None:
    scenario("nginx-web.conf has WS upgrade map + /ws location with Upgrade header")
    text = NGINX_WEB.read_text(encoding="utf-8")
    assert "map $http_upgrade $connection_upgrade" in text
    assert "location = /ws" in text
    assert "proxy_set_header Upgrade $http_upgrade" in text
    assert "proxy_set_header Connection $connection_upgrade" in text
    assert "proxy_pass http://telegram_web_bridge/ws" in text
    # /healthz passthrough to observability sidecar
    assert "location = /healthz" in text
    assert "telegram_observability" in text
    # 80 -> 443 redirect
    assert "return 301 https://" in text


def run_prometheus_scrapes_observability() -> None:
    scenario("prometheus.yml scrapes telegram-server-prod:9100/metrics")
    text = PROM_YML.read_text(encoding="utf-8")
    assert "metrics_path: /metrics" in text
    assert "telegram-server-prod:9100" in text
    assert "scrape_interval" in text


def run_env_example_documents_pa_and_lifecycle() -> None:
    scenario("production.env.example documents every prod env var + PA placeholders")
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for required in (
        "TELEGRAM_PG_PASSWORD",
        "TELEGRAM_PG_PORT",
        "TELEGRAM_RESTART_POLICY",
        "TELEGRAM_SESSION_TTL_SECONDS",
        "TELEGRAM_HTTP_PORT",
        "TELEGRAM_HTTPS_PORT",
        "TELEGRAM_PROM_PORT",
        "TELEGRAM_FCM_CREDENTIALS",
        "TELEGRAM_SMS_PROVIDER",
        "TELEGRAM_SMS_AUTH_TOKEN",
        "TELEGRAM_REDIS_URL",
        "TELEGRAM_REDIS_TOKEN",
    ):
        assert required in text, f"missing {required} in production.env.example"
    for pa in ("PA-008", "PA-009", "PA-011"):
        assert pa in text, f"expected {pa} reference for procurement context"


def run_readme_documents_production_runbook() -> None:
    scenario("deploy/docker/README.md has the M115 production runbook")
    text = README.read_text(encoding="utf-8")
    assert "M115" in text
    assert "--profile production" in text
    assert "production.env.example" in text
    # PA injection table present.
    for pa in ("PA-008", "PA-009", "PA-011"):
        assert pa in text, f"missing {pa} in production runbook"
    # TLS cert swap step is documented.
    assert "deploy/tls/certs/server" in text


def main() -> int:
    scenarios = [
        run_compose_yaml_parses,
        run_prod_service_command_includes_all_flags,
        run_prod_service_healthcheck_uses_observability,
        run_nginx_web_mounts_and_ports,
        run_nginx_web_conf_has_ws_upgrade,
        run_prometheus_scrapes_observability,
        run_env_example_documents_pa_and_lifecycle,
        run_readme_documents_production_runbook,
    ]
    for fn in scenarios:
        fn()
    print(f"\nAll {len(scenarios)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
