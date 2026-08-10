from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_owned_account(db: Session, account_id: int, current_user: models.User) -> models.Account:
    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id, models.Account.user_id == current_user.id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("", response_model=schemas.TransactionOut, status_code=201)
def create_transaction(
    body: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    from_account = _get_owned_account(db, body.from_account_id, current_user)
    if from_account.balance < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    to_account_id = body.to_account_id
    payee = body.payee

    if body.type == "transfer":
        if body.to_account_id is None:
            raise HTTPException(status_code=400, detail="to_account_id is required for a transfer")
        to_account = _get_owned_account(db, body.to_account_id, current_user)
        from_account.balance -= body.amount
        to_account.balance += body.amount
    elif body.type == "bill_payment":
        if not body.payee:
            raise HTTPException(status_code=400, detail="payee is required for a bill payment")
        from_account.balance -= body.amount
    elif body.type == "beneficiary_transfer":
        if body.beneficiary_id is None:
            raise HTTPException(
                status_code=400, detail="beneficiary_id is required for a beneficiary transfer"
            )
        beneficiary = (
            db.query(models.Beneficiary)
            .filter(
                models.Beneficiary.id == body.beneficiary_id,
                models.Beneficiary.owner_user_id == current_user.id,
            )
            .first()
        )
        if beneficiary is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")

        to_account = (
            db.query(models.Account)
            .filter(
                models.Account.user_id == beneficiary.beneficiary_user_id,
                models.Account.type == "checking",
            )
            .first()
        )
        if to_account is None:
            raise HTTPException(status_code=400, detail="Beneficiary has no checking account")

        from_account.balance -= body.amount
        to_account.balance += body.amount
        to_account_id = to_account.id
        payee = beneficiary.nickname or beneficiary.beneficiary_user.email
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported transaction type: {body.type}")

    transaction = models.Transaction(
        user_id=current_user.id,
        type=body.type,
        amount=body.amount,
        from_account_id=body.from_account_id,
        to_account_id=to_account_id,
        payee=payee,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == current_user.id)
        .order_by(models.Transaction.created_at.desc())
        .all()
    )
