"""Regression checks for the canonical App payment interface boundary."""


def test_app_payment_routes_are_canonical(client):
    paths = {route.path for route in client.app.routes}

    assert "/api/v1/app/payments/checkout-sessions" in paths
    assert "/api/v1/app/payments/checkout-sessions/{checkout_session_id}" in paths
    assert "/api/v1/app/payments/checkout/{signed_token}/confirm" in paths
    assert "/api/v1/app/payment-methods" in paths
    assert "/api/v1/app/payments/webhooks/mercadopago" in paths
    assert "/api/v1/app/payments/webhooks/sim" in paths

    legacy_paths = {
        "/api/v1/app/wallet/payments/create",
        "/api/v1/app/wallet/payments/create-mp",
        "/api/v1/app/wallet/payments/{order_id}/status",
        "/api/v1/app/wallet/payments/webhook",
        "/api/v1/app/wallet/payments/webhook-mp",
        "/api/v1/app/wallet/payments/sim-webhook",
        "/api/v1/app/wallet/saved-payment-methods",
    }
    assert paths.isdisjoint(legacy_paths)
