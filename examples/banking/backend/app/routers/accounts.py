from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(
    type: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Account).filter(models.Account.user_id == current_user.id)
    if type is not None:
        query = query.filter(models.Account.type == type)
    return query.all()


@router.get("/{account_id}", response_model=schemas.AccountOut)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id, models.Account.user_id == current_user.id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/{account_id}/statement", response_model=schemas.Message)
def request_statement(
    account_id: int,
    body: schemas.StatementRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id, models.Account.user_id == current_user.id)
        .first()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    # Simulated — a real backend would enqueue an email/export job here.
    return schemas.Message(
        message=f"Statement for account {account_id} ({body.period}) queued for delivery."
    )
