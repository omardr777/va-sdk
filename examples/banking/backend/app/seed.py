"""Convenience script: creates a fixed demo user (with default accounts/cards
provisioned automatically) for manual testing.

Usage: python -m app.seed
"""

from . import models
from .database import Base, SessionLocal, engine
from .provisioning import create_user_with_defaults

DEMO_EMAIL = "demo@bankco.io"
DEMO_PASSWORD = "demo1234"


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        if existing:
            print(f"Demo user already exists: {DEMO_EMAIL}")
            return

        create_user_with_defaults(db, DEMO_EMAIL, DEMO_PASSWORD)
        db.commit()
        print(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
