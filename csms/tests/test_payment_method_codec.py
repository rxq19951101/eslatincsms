"""PAY-MP-001 BE-P0-1 payment-method codec compatibility coverage."""

from __future__ import annotations

import pytest

from app.services.payment_method_codec import (
    decode_payment_method_brand,
    encode_payment_method_brand,
)


@pytest.mark.parametrize(
    "payment_type",
    ["credit_card", "debit_card", "prepaid_card"],
)
def test_codec_round_trips_all_supported_payment_types(payment_type):
    encoded = encode_payment_method_brand("Master", payment_type)

    assert encoded == f"v1:master:{payment_type}"
    assert decode_payment_method_brand(encoded).brand == "master"
    assert decode_payment_method_brand(encoded).payment_type == payment_type


def test_codec_reads_legacy_brand_without_guessing_payment_type():
    descriptor = decode_payment_method_brand("Visa")

    assert descriptor.brand == "visa"
    assert descriptor.payment_type is None


def test_codec_reads_unknown_versioned_type_without_guessing():
    descriptor = decode_payment_method_brand("v1:visa:crypto_card")

    assert descriptor.brand == "visa"
    assert descriptor.payment_type is None


@pytest.mark.parametrize(
    ("brand", "payment_type"),
    [
        ("", "credit_card"),
        ("visa:unsafe", "credit_card"),
        ("visa", "crypto_card"),
        ("x" * 64, "prepaid_card"),
    ],
)
def test_codec_rejects_invalid_or_oversized_new_metadata(brand, payment_type):
    with pytest.raises(ValueError):
        encode_payment_method_brand(brand, payment_type)


@pytest.mark.parametrize("value", [None, "", "unsafe:value", "vi\nsa"])
def test_codec_invalid_legacy_values_have_no_card_facts(value):
    descriptor = decode_payment_method_brand(value)

    assert descriptor.brand is None
    assert descriptor.payment_type is None
