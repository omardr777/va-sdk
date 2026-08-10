from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, engine
from .routers import accounts, auth, beneficiaries, cards, transactions

Base.metadata.create_all(bind=engine)

app = FastAPI(title="BankCo API")

# Dev-only: allows the local Vite frontend to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(cards.router)
app.include_router(beneficiaries.router)
app.include_router(transactions.router)


@app.get("/health")
def health():
    return {"status": "ok"}
