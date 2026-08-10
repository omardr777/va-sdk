import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    balance: float


class StatementRequest(BaseModel):
    period: str = "last_month"


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    last_four: str
    status: str


class CardCancelRequest(BaseModel):
    reason: str | None = None


class FraudReportRequest(BaseModel):
    transaction_amount: float | None = None


class BeneficiaryCreate(BaseModel):
    email: EmailStr
    nickname: str | None = None


class BeneficiaryOut(BaseModel):
    id: int
    email: str
    nickname: str | None


class TransactionCreate(BaseModel):
    type: str  # transfer | bill_payment | beneficiary_transfer
    amount: float
    from_account_id: int
    to_account_id: int | None = None
    beneficiary_id: int | None = None
    payee: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    amount: float
    from_account_id: int | None
    to_account_id: int | None
    payee: str | None
    created_at: datetime.datetime


class Message(BaseModel):
    message: str
