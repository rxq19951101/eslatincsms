"""Contract and isolation tests for App favorite sites."""

from decimal import Decimal
import uuid

from app.core.auth import create_access_token, get_password_hash
from app.database.models import AppUser, AppUserFavoriteSite


def _headers(db_session, email: str) -> tuple[dict[str, str], AppUser]:
    user = AppUser(
        email=email,
        password_hash=get_password_hash("test-password"),
        email_verified=True,
        balance=Decimal("0.00"),
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token({
        "user_id": str(user.id),
        "user_type": "app_user",
        "aud": "app",
    })
    return {"Authorization": f"Bearer {token}"}, user


def test_favorite_site_lifecycle_is_idempotent_and_personal(
    client,
    db_session,
    sample_site,
    sample_commercial_charge_point,
):
    first_headers, first_user = _headers(db_session, "favorite-one@example.test")
    second_headers, _ = _headers(db_session, "favorite-two@example.test")
    endpoint = f"/api/v1/app/favorites/{sample_site.id}"

    assert client.put(endpoint, headers=first_headers).status_code == 200
    assert client.put(endpoint, headers=first_headers).status_code == 200
    assert db_session.query(AppUserFavoriteSite).filter(
        AppUserFavoriteSite.app_user_id == first_user.id,
        AppUserFavoriteSite.site_id == sample_site.id,
    ).count() == 1

    first_list = client.get("/api/v1/app/favorites", headers=first_headers)
    second_list = client.get("/api/v1/app/favorites", headers=second_headers)
    assert first_list.status_code == 200
    assert [item["id"] for item in first_list.json()] == [str(sample_site.id)]
    assert first_list.json()[0]["is_favorite"] is True
    assert second_list.json() == []

    detail = client.get(f"/api/v1/app/sites/{sample_site.id}", headers=first_headers)
    assert detail.status_code == 200
    assert detail.json()["is_favorite"] is True

    assert client.delete(endpoint, headers=first_headers).status_code == 200
    assert client.delete(endpoint, headers=first_headers).status_code == 200
    assert client.get("/api/v1/app/favorites", headers=first_headers).json() == []


def test_favorite_rejects_inactive_or_missing_site(client, db_session, sample_site):
    headers, _ = _headers(db_session, "favorite-invalid@example.test")
    sample_site.is_active = False
    db_session.commit()

    inactive = client.put(f"/api/v1/app/favorites/{sample_site.id}", headers=headers)
    missing = client.put(f"/api/v1/app/favorites/{uuid.uuid4()}", headers=headers)
    assert inactive.status_code == 404
    assert missing.status_code == 404


def test_favorites_require_app_auth(client, sample_site):
    assert client.get("/api/v1/app/favorites").status_code == 401
    assert client.put(f"/api/v1/app/favorites/{sample_site.id}").status_code == 401
