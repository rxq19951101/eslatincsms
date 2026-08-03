#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROD_ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
FIRST_BOOT=false

if [ "${1:-}" = "--first-boot" ]; then
    FIRST_BOOT=true
elif [ -n "${1:-}" ]; then
    echo "Usage: $0 [--first-boot]" >&2
    exit 2
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE does not exist. Copy .env.production.example first." >&2
    exit 1
fi

value_for() {
    local key="$1"
    awk -F= -v wanted="$key" '
        $1 == wanted {
            sub(/^[^=]*=/, "")
            gsub(/^['\''"]|['\''"]$/, "")
            print
            exit
        }
    ' "$ENV_FILE"
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_value() {
    local key="$1"
    local value
    value="$(value_for "$key")"
    [ -n "$value" ] || fail "$key must be set"
    case "$value" in
        *CHANGE_ME*|*change-me*|*your-*|*placeholder*)
            fail "$key still contains a placeholder"
            ;;
    esac
}

require_min_length() {
    local key="$1"
    local minimum="$2"
    local value
    value="$(value_for "$key")"
    [ "${#value}" -ge "$minimum" ] || fail "$key must contain at least $minimum characters"
}

require_https() {
    local key="$1"
    local value
    value="$(value_for "$key")"
    case "$value" in
        https://*) ;;
        *) fail "$key must use https://" ;;
    esac
    case "$value" in
        *example.com*|*localhost*|*127.0.0.1*) fail "$key must use the real production hostname" ;;
    esac
}

require_public_hostname() {
    local key="$1"
    local value
    value="$(value_for "$key")"
    case "$value" in
        *://*|*/*|*:*|*" "*|*"*"*|.*|*.) fail "$key must be a bare public hostname without scheme, port, path, wildcard, or surrounding dot" ;;
    esac
    case "$value" in
        *.*) ;;
        *) fail "$key must be a fully qualified public hostname" ;;
    esac
    if [[ ! "$value" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]; then
        fail "$key contains invalid hostname characters or labels"
    fi
    case "$value" in
        example.com|*.example.com|localhost|127.*) fail "$key must use the real production hostname" ;;
    esac
}

require_email_address() {
    local key="$1"
    local value
    value="$(value_for "$key")"
    case "$value" in
        *@*.*) ;;
        *) fail "$key must be a valid email address" ;;
    esac
    case "$value" in
        *" "*) fail "$key must not contain spaces" ;;
    esac
}

for key in \
    ENVIRONMENT ADMIN_DOMAIN API_DOMAIN ACME_EMAIL PROXY_BIND_ADDRESS \
    PUBLIC_HTTP_PORT PUBLIC_HTTPS_PORT DB_USER DB_PASSWORD DB_NAME DATABASE_URL \
    REDIS_PASSWORD REDIS_URL SECRET_KEY ENCRYPTION_KEY ENCRYPTION_SALT \
    CORS_ALLOW_ORIGINS PUBLIC_API_BASE_URL NEXT_PUBLIC_CSMS_HTTP \
    NEXT_PUBLIC_API_BASE_URL SMTP_HOST SMTP_USER SMTP_PASSWORD SMTP_FROM; do
    require_value "$key"
done

[ "$(value_for ENVIRONMENT)" = "production" ] || fail "ENVIRONMENT must be production"
require_public_hostname ADMIN_DOMAIN
require_public_hostname API_DOMAIN
admin_domain="$(value_for ADMIN_DOMAIN)"
api_domain="$(value_for API_DOMAIN)"
[ "$admin_domain" != "$api_domain" ] || fail "ADMIN_DOMAIN and API_DOMAIN must be different"
case "$(value_for ACME_EMAIL)" in
    *@*.*) ;;
    *) fail "ACME_EMAIL must be a valid operational email address" ;;
esac
case "$(value_for ACME_EMAIL)" in
    *example.com*|*CHANGE_ME*) fail "ACME_EMAIL must use the real operational address" ;;
esac
[ "$(value_for PROXY_BIND_ADDRESS)" = "0.0.0.0" ] || fail "PROXY_BIND_ADDRESS must be 0.0.0.0"
[ "$(value_for PUBLIC_HTTP_PORT)" = "80" ] || fail "PUBLIC_HTTP_PORT must be 80 for HTTP redirect and ACME"
[ "$(value_for PUBLIC_HTTPS_PORT)" = "443" ] || fail "PUBLIC_HTTPS_PORT must be 443"
require_min_length DB_PASSWORD 16
require_min_length REDIS_PASSWORD 16
require_min_length SECRET_KEY 32
require_min_length ENCRYPTION_KEY 32
require_min_length ENCRYPTION_SALT 16

case "$(value_for DATABASE_URL)" in
    postgresql://*@db:5432/*) ;;
    *) fail "DATABASE_URL must target the Compose db service" ;;
esac
case "$(value_for REDIS_URL)" in
    redis://:*@redis:6379/*) ;;
    *) fail "REDIS_URL must include the password and target the Compose redis service" ;;
esac

require_https PUBLIC_API_BASE_URL
require_https NEXT_PUBLIC_CSMS_HTTP
require_https NEXT_PUBLIC_API_BASE_URL

admin_origin="https://$admin_domain"
api_origin="https://$api_domain"
[ "$(value_for CORS_ALLOW_ORIGINS)" = "$admin_origin" ] || fail "CORS_ALLOW_ORIGINS must equal $admin_origin"
[ "$(value_for PUBLIC_API_BASE_URL)" = "$api_origin" ] || fail "PUBLIC_API_BASE_URL must equal $api_origin"
[ "$(value_for NEXT_PUBLIC_CSMS_HTTP)" = "$api_origin" ] || fail "NEXT_PUBLIC_CSMS_HTTP must equal $api_origin"
[ "$(value_for NEXT_PUBLIC_API_BASE_URL)" = "$api_origin" ] || fail "NEXT_PUBLIC_API_BASE_URL must equal $api_origin"

cors="$(value_for CORS_ALLOW_ORIGINS)"
case "$cors" in
    "*"|*"*"*) fail "CORS_ALLOW_ORIGINS must not contain *" ;;
esac
case "$cors" in
    *https://*) ;;
    *) fail "CORS_ALLOW_ORIGINS must contain the HTTPS Admin origin" ;;
esac

[ "$(value_for ENABLE_WEBSOCKET_TRANSPORT)" = "true" ] || fail "ENABLE_WEBSOCKET_TRANSPORT must be true"
[ "$(value_for ENABLE_MQTT_TRANSPORT)" = "false" ] || fail "ENABLE_MQTT_TRANSPORT must be false"
[ "$(value_for ENABLE_HTTP_TRANSPORT)" = "false" ] || fail "ENABLE_HTTP_TRANSPORT must be false"

if [ "$FIRST_BOOT" = true ]; then
    require_value CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL
    require_value CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD
    require_value CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL
    require_value CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD
    require_email_address CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL
    require_email_address CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL
    require_min_length CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD 16
    require_min_length CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD 16
    [ "$(value_for CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL)" != "$(value_for CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL)" ] || fail "Bootstrap admin emails must be different"
    [ "$(value_for CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD)" != "$(value_for CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD)" ] || fail "Bootstrap admin passwords must be different"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
echo "Production environment validation passed."
