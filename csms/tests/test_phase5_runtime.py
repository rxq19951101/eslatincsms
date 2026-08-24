def test_liveness_and_readiness_probes(client):
    live = client.get("/livez")
    assert live.status_code == 200
    assert live.json()["ok"] is True

    ready = client.get("/readyz")
    assert ready.status_code in (200, 503)
    if ready.status_code == 200:
        assert ready.json()["ok"] is True


def test_trace_id_is_returned(client):
    response = client.get("/livez", headers={"X-Trace-ID": "phase5-trace"})
    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == "phase5-trace"
