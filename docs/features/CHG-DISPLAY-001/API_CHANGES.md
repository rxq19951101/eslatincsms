# API contract

Additive changes only under `/api/v1`.

`POST /api/v1/sites/{site_id}/charge-points` accepts `display_code`, optional
`display_name`, and optional `location_hint`. EVSE `physical_reference` remains
the public connector label.

App site detail charge-point items add:

```json
{
  "display_code": "A01",
  "display_name": null,
  "location_hint": "P2 / bay 42",
  "connectors": [{"physical_reference": "A01-1"}]
}
```

UUID fields may remain opaque API relation identifiers. OCPP credentials and
identities are not added to the driver-facing site payload.
