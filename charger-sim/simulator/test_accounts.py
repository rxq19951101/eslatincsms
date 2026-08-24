"""Environment-only compatibility helpers for legacy imports.

No account, card, or provider credential is read from a repository file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TestIdentity:
    __test__ = False

    email: str
    password: str


def get_test_identity(prefix: str) -> TestIdentity:
    normalized = prefix.upper()
    email_name = f"{normalized}_EMAIL"
    password_name = f"{normalized}_PASSWORD"
    email = os.environ.get(email_name)
    password = os.environ.get(password_name)
    if not email or not password:
        raise RuntimeError(f"Set {email_name} and {password_name} in the environment")
    return TestIdentity(email=email, password=password)


def load_test_accounts(*args, **kwargs):
    raise RuntimeError(
        "test_accounts.yml is no longer supported; inject scenario credentials through environment variables"
    )
