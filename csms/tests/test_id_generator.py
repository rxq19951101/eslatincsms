import re

from app.core.id_generator import generate_site_id


SITE_ID_PATTERN = re.compile(r"^site_[0-9a-f]{16}$")


def test_site_id_is_opaque_ascii_and_does_not_include_business_name() -> None:
    site_id = generate_site_id("默认站点 Bogotá")

    assert SITE_ID_PATTERN.fullmatch(site_id)
    assert "默认站点" not in site_id
    assert "bogot" not in site_id.lower()


def test_site_ids_are_unique_even_for_the_same_name() -> None:
    assert generate_site_id("Same name") != generate_site_id("Same name")
