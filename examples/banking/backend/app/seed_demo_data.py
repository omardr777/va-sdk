"""Seeds several demo users, each with realistic account balances, some
transaction history, beneficiary links between them, and a bit of card
status variety (one cancelled, one flagged for fraud) — enough data to
click around the frontend without registering everything by hand.

Usage: python -m app.seed_demo_data
"""

from . import models
from .database import Base, SessionLocal, engine
from .provisioning import create_user_with_defaults

PASSWORD = "demo1234"

USERS = [
    {"email": "alice@bankco.io", "balances": {"checking": 4200.0, "savings": 15000.0, "credit": 0.0}},
    {"email": "bob@bankco.io", "balances": {"checking": 1800.0, "savings": 3200.0, "credit": 0.0}},
    {"email": "carol@bankco.io", "balances": {"checking": 9600.0, "savings": 500.0, "credit": 0.0}},
    {"email": "dave@bankco.io", "balances": {"checking": 650.0, "savings": 0.0, "credit": 0.0}},
]


def _account(user: models.User, account_type: str) -> models.Account:
    return next(a for a in user.accounts if a.type == account_type)


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users: dict[str, models.User] = {}
        created_any = False
        for spec in USERS:
            existing = db.query(models.User).filter(models.User.email == spec["email"]).first()
            if existing:
                users[spec["email"]] = existing
                print(f"Already exists, skipping: {spec['email']}")
                continue
            user = create_user_with_defaults(db, spec["email"], PASSWORD, balances=spec["balances"])
            db.flush()
            users[spec["email"]] = user
            created_any = True

        if not created_any:
            print("All demo users already exist — nothing new to seed.")
            return

        db.flush()
        for user in users.values():
            db.refresh(user)

        alice, bob, carol, dave = (
            users["alice@bankco.io"],
            users["bob@bankco.io"],
            users["carol@bankco.io"],
            users["dave@bankco.io"],
        )

        # --- Beneficiary links ---
        db.add_all(
            [
                models.Beneficiary(owner_user_id=alice.id, beneficiary_user_id=bob.id, nickname="Bob"),
                models.Beneficiary(owner_user_id=alice.id, beneficiary_user_id=carol.id, nickname="Carol"),
                models.Beneficiary(owner_user_id=bob.id, beneficiary_user_id=alice.id, nickname="Alice"),
                models.Beneficiary(owner_user_id=carol.id, beneficiary_user_id=dave.id, nickname="Dave"),
            ]
        )

        # --- Transaction history (mutates balances directly, mirroring the
        # /transactions endpoint's logic, since this is trusted seed data) ---
        alice_checking = _account(alice, "checking")
        alice_savings = _account(alice, "savings")
        bob_checking = _account(bob, "checking")
        carol_checking = _account(carol, "checking")
        dave_checking = _account(dave, "checking")

        # Alice moves money into her own savings
        alice_checking.balance -= 500.0
        alice_savings.balance += 500.0
        db.add(
            models.Transaction(
                user_id=alice.id,
                type="transfer",
                amount=500.0,
                from_account_id=alice_checking.id,
                to_account_id=alice_savings.id,
            )
        )

        # Alice pays rent
        alice_checking.balance -= 1200.0
        db.add(
            models.Transaction(
                user_id=alice.id,
                type="bill_payment",
                amount=1200.0,
                from_account_id=alice_checking.id,
                payee="Riverside Apartments",
            )
        )

        # Alice sends Bob money for a shared expense
        alice_checking.balance -= 150.0
        bob_checking.balance += 150.0
        db.add(
            models.Transaction(
                user_id=alice.id,
                type="beneficiary_transfer",
                amount=150.0,
                from_account_id=alice_checking.id,
                to_account_id=bob_checking.id,
                payee="Bob",
            )
        )

        # Carol sends Dave money
        carol_checking.balance -= 300.0
        dave_checking.balance += 300.0
        db.add(
            models.Transaction(
                user_id=carol.id,
                type="beneficiary_transfer",
                amount=300.0,
                from_account_id=carol_checking.id,
                to_account_id=dave_checking.id,
                payee="Dave",
            )
        )

        # Bob pays a utility bill
        bob_checking.balance -= 85.5
        db.add(
            models.Transaction(
                user_id=bob.id,
                type="bill_payment",
                amount=85.5,
                from_account_id=bob_checking.id,
                payee="CityPower Electric",
            )
        )

        # --- Card status variety ---
        dave_debit = next(c for c in dave.cards if c.type == "debit")
        dave_debit.status = "cancelled"

        bob_credit = next(c for c in bob.cards if c.type == "credit")
        db.add(models.FraudReport(card_id=bob_credit.id, transaction_amount=42.99))
        bob_credit.status = "cancelled"

        db.commit()
        print("Seeded demo users (password 'demo1234' for all):")
        for spec in USERS:
            print(f"  {spec['email']}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
