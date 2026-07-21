import pytest
import bcrypt

from app.core import auth, security


def test_bcrypt_hash_and_verify_use_one_implementation():
    password = "correct horse battery staple"
    password_hash = auth.get_password_hash(password)

    assert password_hash.startswith(auth.BCRYPT_SHA256_SCHEME)
    assert auth.verify_password(password, password_hash) is True
    assert auth.verify_password("wrong password", password_hash) is False
    assert security.get_password_hash is auth.get_password_hash
    assert security.verify_password is auth.verify_password


def test_password_hash_supports_128_ascii_and_multibyte_characters():
    ascii_password = "a" * auth.PASSWORD_MAX_CHARACTERS
    multibyte_password = "密" * auth.PASSWORD_MAX_CHARACTERS

    ascii_hash = auth.get_password_hash(ascii_password)
    multibyte_hash = auth.get_password_hash(multibyte_password)
    assert auth.verify_password(ascii_password, ascii_hash) is True
    assert auth.verify_password(multibyte_password, multibyte_hash) is True

    with pytest.raises(ValueError, match="must not be empty"):
        auth.get_password_hash("")
    with pytest.raises(ValueError, match="at most 128 characters"):
        auth.get_password_hash("a" * 129)


@pytest.mark.parametrize(
    ("password", "password_hash"),
    [
        ("password", "not-a-bcrypt-hash"),
        ("password", "$2b$12$C6UzMDM.H6dfI/f/IKcEe.yrM4vrVbE4hM9xemT0M81YmsYeL2a72"),
        ("password", "$csms-bcrypt-sha256$v=2$2b$12$invalid"),
        ("", "$2b$12$invalid"),
        ("a" * 129, "$csms-bcrypt-sha256$v=1$2b$12$invalid"),
        (None, "$2b$12$invalid"),
        ("password", None),
    ],
)
def test_password_verification_rejects_invalid_input_without_raising(
    password, password_hash
):
    assert auth.verify_password(password, password_hash) is False


def test_wrong_password_is_rejected_for_versioned_hash():
    password_hash = auth.get_password_hash("正确密码-123456")
    assert auth.verify_password("错误密码-123456", password_hash) is False


def test_legacy_raw_bcrypt_accepts_correct_and_rejects_wrong_password():
    password = "legacy-admin-password"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )

    assert legacy_hash.startswith("$2b$")
    assert auth.verify_password(password, legacy_hash) is True
    assert auth.verify_password("wrong-password", legacy_hash) is False


def test_legacy_raw_bcrypt_rejects_passwords_over_72_utf8_bytes():
    first_72_bytes = "a" * auth.BCRYPT_LEGACY_MAX_BYTES
    legacy_hash = bcrypt.hashpw(
        first_72_bytes.encode("utf-8"), bcrypt.gensalt()
    ).decode("ascii")

    assert auth.verify_password(first_72_bytes + "suffix", legacy_hash) is False
    assert auth.verify_password("密" * 25, legacy_hash) is False


def test_new_hash_generation_never_emits_legacy_raw_bcrypt():
    password_hash = auth.get_password_hash("new-format-password")
    assert password_hash.startswith(auth.BCRYPT_SHA256_SCHEME)
    assert auth.LEGACY_BCRYPT_PATTERN.fullmatch(password_hash) is None
