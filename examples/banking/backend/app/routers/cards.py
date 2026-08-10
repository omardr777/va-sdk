from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/cards", tags=["cards"])


def _get_owned_card(db: Session, card_id: int, current_user: models.User) -> models.Card:
    card = (
        db.query(models.Card)
        .filter(models.Card.id == card_id, models.Card.user_id == current_user.id)
        .first()
    )
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.get("", response_model=list[schemas.CardOut])
def list_cards(
    type: str | None = None,
    last_four: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Card).filter(models.Card.user_id == current_user.id)
    if type is not None:
        query = query.filter(models.Card.type == type)
    if last_four is not None:
        query = query.filter(models.Card.last_four == last_four)
    return query.all()


@router.post("/{card_id}/cancel", response_model=schemas.CardOut)
def cancel_card(
    card_id: int,
    body: schemas.CardCancelRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    card = _get_owned_card(db, card_id, current_user)
    if card.status == "cancelled":
        raise HTTPException(status_code=400, detail="Card is already cancelled")
    card.status = "cancelled"
    db.commit()
    db.refresh(card)
    return card


@router.post("/{card_id}/replace", response_model=schemas.CardOut)
def replace_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    old_card = _get_owned_card(db, card_id, current_user)
    old_card.status = "cancelled"

    # Deterministic-but-fake new last-four so repeated replacements don't collide.
    existing_last_fours = {
        c.last_four for c in db.query(models.Card).filter(models.Card.user_id == current_user.id)
    }
    new_last_four = None
    for candidate in range(1000, 10000):
        candidate_str = f"{candidate:04d}"
        if candidate_str not in existing_last_fours:
            new_last_four = candidate_str
            break
    if new_last_four is None:
        raise HTTPException(status_code=500, detail="Could not allocate a new card number")

    new_card = models.Card(
        user_id=current_user.id,
        type=old_card.type,
        last_four=new_last_four,
        status="inactive",
    )
    db.add(new_card)
    db.commit()
    db.refresh(new_card)
    return new_card


@router.post("/{card_id}/activate", response_model=schemas.CardOut)
def activate_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    card = _get_owned_card(db, card_id, current_user)
    if card.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot activate a cancelled card")
    card.status = "active"
    db.commit()
    db.refresh(card)
    return card


@router.post("/{card_id}/reset-pin", response_model=schemas.Message)
def reset_pin(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    card = _get_owned_card(db, card_id, current_user)
    if card.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reset PIN on a cancelled card")
    # PIN itself isn't modeled — this simulates the request being queued.
    return schemas.Message(message=f"PIN reset requested for card {card_id}.")


@router.post("/{card_id}/fraud-reports", response_model=schemas.Message)
def report_fraud(
    card_id: int,
    body: schemas.FraudReportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    card = _get_owned_card(db, card_id, current_user)
    report = models.FraudReport(card_id=card.id, transaction_amount=body.transaction_amount)
    db.add(report)
    card.status = "cancelled"  # freeze the card pending investigation
    db.commit()
    return schemas.Message(message=f"Fraud report filed for card {card_id}; card frozen.")
