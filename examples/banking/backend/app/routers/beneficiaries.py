from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


@router.get("", response_model=list[schemas.BeneficiaryOut])
def list_beneficiaries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.Beneficiary)
        .filter(models.Beneficiary.owner_user_id == current_user.id)
        .all()
    )
    return [
        schemas.BeneficiaryOut(id=b.id, email=b.beneficiary_user.email, nickname=b.nickname)
        for b in rows
    ]


@router.post("", response_model=schemas.BeneficiaryOut, status_code=201)
def add_beneficiary(
    body: schemas.BeneficiaryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if body.email == current_user.email:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a beneficiary")

    target = db.query(models.User).filter(models.User.email == body.email).first()
    if target is None:
        raise HTTPException(status_code=404, detail="No BankCo user with that email")

    existing = (
        db.query(models.Beneficiary)
        .filter(
            models.Beneficiary.owner_user_id == current_user.id,
            models.Beneficiary.beneficiary_user_id == target.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Beneficiary already added")

    beneficiary = models.Beneficiary(
        owner_user_id=current_user.id, beneficiary_user_id=target.id, nickname=body.nickname
    )
    db.add(beneficiary)
    db.commit()
    db.refresh(beneficiary)
    return schemas.BeneficiaryOut(id=beneficiary.id, email=target.email, nickname=beneficiary.nickname)


@router.delete("/{beneficiary_id}", status_code=204)
def remove_beneficiary(
    beneficiary_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    beneficiary = (
        db.query(models.Beneficiary)
        .filter(
            models.Beneficiary.id == beneficiary_id,
            models.Beneficiary.owner_user_id == current_user.id,
        )
        .first()
    )
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    db.delete(beneficiary)
    db.commit()
