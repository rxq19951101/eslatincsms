"""Encryption boundary for checkout state and one-time provider tokens."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class PaymentTokenCryptoError(RuntimeError):
    """Safe encryption error that never includes plaintext or key material."""


class PaymentTokenCipher:
    def __init__(self, encryption_key: str) -> None:
        if not encryption_key or not encryption_key.strip():
            raise PaymentTokenCryptoError("Payment token encryption key is required")
        try:
            self._fernet = Fernet(encryption_key.strip().encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            raise PaymentTokenCryptoError("Invalid payment token encryption key") from exc

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str) or not plaintext:
            raise PaymentTokenCryptoError("Payment token plaintext is required")
        try:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        except Exception as exc:
            raise PaymentTokenCryptoError("Unable to encrypt payment token") from exc

    def decrypt(self, ciphertext: str | bytes) -> str:
        if not ciphertext:
            raise PaymentTokenCryptoError("Payment token ciphertext is required")
        encoded = ciphertext.encode("ascii") if isinstance(ciphertext, str) else ciphertext
        try:
            return self._fernet.decrypt(encoded).decode("utf-8")
        except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
            raise PaymentTokenCryptoError("Unable to decrypt payment token") from exc
