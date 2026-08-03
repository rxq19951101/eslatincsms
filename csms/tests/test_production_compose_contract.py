from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_has_first_boot_and_private_network_gates():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "db-role-init:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD" in compose
    assert "CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD" in compose
    assert '"${CSMS_BIND_ADDRESS:-127.0.0.1}:${CSMS_PORT:-9000}:9000"' not in compose
    assert '"${ADMIN_BIND_ADDRESS:-127.0.0.1}:${ADMIN_PORT:-3000}:3000"' not in compose
    assert "proxy:" in compose
    assert '["CMD", "curl", "--fail"' in compose
    assert "qr_data:/data/qr" in compose


def test_production_environment_example_contains_no_runtime_secret_file():
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "DB_PASSWORD=CHANGE_ME" in example
    assert "SECRET_KEY=CHANGE_ME" in example
    assert "CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD=" in example
    assert ".env.production" in gitignore
