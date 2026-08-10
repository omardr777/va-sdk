"""Shared "new BankCo customer" provisioning logic, used by both the
/auth/register endpoint and the seed scripts so a user always ends up with
the same realistic starting shape: 3 accounts + 2 cards."""

import random

from sqlalchemy.orm import Session

from . import auth, models

DEFAULT_ACCOUNT_TYPES = ["checking", "savings", "credit"]
DEFAULT_STARTING_BALANCE = {"checking": 2500.0, "savings": 8000.0, "credit": 0.0}
DEFAULT_CARD_TYPES = ["debit", "credit"]


def _random_last_four() -> str:
    return f"{random.randint(0, 9999):04d}"


def create_user_with_defaults(
    db: Session, email: str, password: str, balances: dict[str, float] | None = None
) -> models.User:
    balances = balances or DEFAULT_STARTING_BALANCE

    user = models.User(email=email, hashed_password=auth.hash_password(password))
    db.add(user)
    db.flush()  # populate user.id before creating dependent rows

    for account_type in DEFAULT_ACCOUNT_TYPES:
        db.add(
            models.Account(
                user_id=user.id,
                type=account_type,
                balance=balances.get(account_type, 0.0),
            )
        )
    for card_type in DEFAULT_CARD_TYPES:
        db.add(models.Card(user_id=user.id, type=card_type, last_four=_random_last_four()))

    return user
