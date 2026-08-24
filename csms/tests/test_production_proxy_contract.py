from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _service_block(compose: str, service: str, next_service: str) -> str:
    return compose.split(f"\n  {service}:\n", 1)[1].split(
        f"\n  {next_service}:\n", 1
    )[0]


def test_only_proxy_publishes_production_ports():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    csms = _service_block(compose, "csms", "admin")
    admin = _service_block(compose, "admin", "proxy")
    proxy = compose.split("\n  proxy:\n", 1)[1].split("\nvolumes:\n", 1)[0]

    assert "\n    ports:" not in csms
    assert "\n    ports:" not in admin
    assert 'PUBLIC_HTTP_PORT:-80}:80/tcp' in proxy
    assert 'PUBLIC_HTTPS_PORT:-443}:443/tcp' in proxy
    assert 'PUBLIC_HTTPS_PORT:-443}:443/udp' in proxy
    assert "condition: service_healthy" in proxy


def test_caddy_routes_admin_api_and_websocket_without_path_rewrite():
    caddyfile = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")

    assert "{$ADMIN_DOMAIN}" in caddyfile
    assert "reverse_proxy admin:3000" in caddyfile
    assert "{$API_DOMAIN}" in caddyfile
    assert "reverse_proxy csms:9000" in caddyfile
    assert "Strict-Transport-Security" in caddyfile
    assert "handle_path" not in caddyfile
    assert "uri strip_prefix" not in caddyfile


def test_production_template_and_preflight_define_public_tls_contract():
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    validator = (ROOT / "scripts/validate_prod_env.sh").read_text(encoding="utf-8")

    for key in (
        "ADMIN_DOMAIN",
        "API_DOMAIN",
        "ACME_EMAIL",
        "PROXY_BIND_ADDRESS",
        "PUBLIC_HTTP_PORT",
        "PUBLIC_HTTPS_PORT",
    ):
        assert f"{key}=" in example
        assert key in validator

    assert 'CORS_ALLOW_ORIGINS must equal $admin_origin' in validator
    assert 'NEXT_PUBLIC_CSMS_HTTP must equal $api_origin' in validator
