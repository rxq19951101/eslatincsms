# Charger simulator

## Manual end-to-end charger

The `manual-simulator` Compose profile defines one unregistered OCPP 1.6J
charger for a manual Admin/App test. Register it in Admin before starting the
container.

Use these values in **Site -> Add charger**:

| Field | Value |
| --- | --- |
| OCPP identity / hardware code | `CO.BOGOTA:MANUAL-CP-001` |
| Vendor | `EsLatin` |
| Model | `Manual-AC-7kW` |
| EVSE ID | `1` |
| Physical reference | `A-01` |
| Connector type | `Type2` |
| Maximum power | `7 kW` |

After Admin returns the one-time OCPP secret, save it only in the ignored root
`.env` file:

```dotenv
MANUAL_SIM_OCPP_IDENTITY=CO.BOGOTA:MANUAL-CP-001
MANUAL_SIM_OCPP_SECRET=replace-with-the-one-time-secret
```

Then start only this charger:

```bash
docker compose --profile manual-simulator up -d manual-charger-sim
docker compose logs -f manual-charger-sim
```

Do not commit the generated OCPP secret.

## Containerized tests

Run the test suite in the dedicated Python 3.11 test image:

```bash
docker build --build-context repository=. --target test \
  -t eslatincsms-charger-sim-test ./charger-sim && \
docker run --rm eslatincsms-charger-sim-test
```

The `test` target inherits from the official `python:3.11-slim` image and uses
its OpenSSL-backed Python runtime. Test-only packages come from
`requirements-test.txt`. The final/default `runtime` target is built from the
runtime dependency stage directly, so it does not contain pytest.

The named `repository` build context supplies the root `docker-compose.yml`
fixture used by the secret-hygiene test. It is copied only into the test target.

This command runs `tests/` plus `smoke_test.py`; the current suite contains 63
tests. Keep urllib3 at the version selected by runtime dependencies: do not
downgrade it or suppress TLS backend warnings globally.
