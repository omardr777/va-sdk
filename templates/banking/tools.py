import httpx

from va_sdk import Tool, Param, Toolkit, ToolError

BANKCO_URL = "http://localhost:8001"


class BankAPI:
    def __init__(self, token: str):
        self.http = httpx.Client(
            base_url=BANKCO_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _check(self, resp):
        if resp.status_code == 401:
            raise ToolError.auth_expired("Session expired. Please sign in again.")
        if resp.status_code >= 400:
            msg = resp.json().get("detail", "Backend request failed")
            if "not found" in str(msg).lower():
                raise ToolError.not_found(str(msg))
            raise ToolError.generic(str(msg))
        return resp.json()

    def get(self, path, **kwargs):
        return self._check(self.http.get(path, **kwargs))

    def post(self, path, json=None):
        return self._check(self.http.post(path, json=json))

    def find_account_id(self, account_type: str) -> int:
        accounts = self.get("/accounts", params={"type": account_type})
        if not accounts:
            raise ToolError.not_found(f"no {account_type} account")
        return accounts[0]["id"]

    def find_card_id(self, card_type: str | None, card_last_four: str) -> int:
        params = {"last_four": card_last_four}
        if card_type:
            params["type"] = card_type
        cards = self.get("/cards", params=params)
        if not cards:
            msg = f"no card ending in {card_last_four}"
            if card_type:
                msg = f"no {card_type} card ending in {card_last_four}"
            raise ToolError.not_found(msg)
        return cards[0]["id"]

    def find_beneficiary(self, name: str) -> dict:
        beneficiaries = self.get("/beneficiaries")
        requested = name.strip().lower()
        for b in beneficiaries:
            if requested in {b.get("nickname", "").lower(), b.get("email", "").lower()}:
                return b
        raise ToolError.not_found(f"no beneficiary named {name}")


tools = [
    Tool(
        name="check_balance",
        description="Check the balance of a bank account.",
        params=[
            Param("account_type", type="string",
                  enum=["checking", "savings", "credit"],
                  description="Type of account to check balance for",
                  prompt="which account"),
        ],
        call=lambda api, account_type: {"balance": api.get("/accounts", params={"type": account_type})[0]["balance"]},
        success_template="Your {account_type} balance is ${balance:.2f}.",
        error_template="Couldn't check your {account_type} balance: {error_message}.",
        input_examples=[{"account_type": "checking"}],
        category="banking",
    ),
    Tool(
        name="transfer_money",
        description="Transfer money between the user's own bank accounts.",
        params=[
            Param("amount", type="number",
                  description="Amount to transfer in dollars",
                  prompt="the amount"),
            Param("from_account", type="string",
                  enum=["checking", "savings"],
                  description="Account to transfer money from",
                  prompt="which account to transfer from"),
            Param("to_account", type="string",
                  enum=["checking", "savings"],
                  description="Account to transfer money to",
                  prompt="which account to transfer to"),
        ],
        call=lambda api, amount, from_account, to_account: api.post(
            "/transactions",
            json={
                "type": "transfer",
                "amount": amount,
                "from_account_id": api.find_account_id(from_account),
                "to_account_id": api.find_account_id(to_account),
            },
        ),
        success_template="Done. Transferred ${amount:.2f} from {from_account} to {to_account}.",
        error_template="Couldn't transfer: {error_message}.",
        input_examples=[
            {"amount": 50, "from_account": "checking", "to_account": "savings"},
        ],
        category="banking",
    ),
    Tool(
        name="cancel_card",
        description="Cancel and deactivate a bank card.",
        params=[
            Param("card_type", type="string",
                  enum=["credit", "debit"],
                  description="Type of card to cancel",
                  prompt="credit or debit"),
            Param("card_last_four", type="string",
                  description="Last 4 digits of the card number",
                  prompt="the last 4 digits"),
            Param("reason", type="string",
                  enum=["lost", "stolen", "damaged", "other"],
                  description="Reason for cancelling",
                  required=False),
        ],
        call=lambda api, card_type, card_last_four, reason=None: api.post(
            f"/cards/{api.find_card_id(card_type, card_last_four)}/cancel",
            json={"reason": reason},
        ),
        success_template="Done. Your {card_type} card ending in {card_last_four} has been cancelled.",
        error_template="Couldn't cancel card: {error_message}.",
        input_examples=[
            {"card_type": "debit", "card_last_four": "1234", "reason": "lost"},
        ],
        category="cards",
    ),
    Tool(
        name="pay_bill",
        description="Pay a bill to a payee.",
        params=[
            Param("payee", type="string",
                  description="Name of the payee",
                  prompt="who to pay"),
            Param("amount", type="number",
                  description="Amount to pay in dollars",
                  prompt="the amount"),
            Param("from_account", type="string",
                  enum=["checking", "savings"],
                  description="Account to pay from",
                  prompt="which account to pay from",
                  required=False),
        ],
        call=lambda api, payee, amount, from_account="checking": api.post(
            "/transactions",
            json={
                "type": "bill_payment",
                "amount": amount,
                "payee": payee,
                "from_account_id": api.find_account_id(from_account),
            },
        ),
        success_template="Done. Paid ${amount:.2f} to {payee}.",
        error_template="Couldn't pay {payee}: {error_message}.",
        input_examples=[
            {"payee": "Electric Company", "amount": 100, "from_account": "checking"},
        ],
        category="banking",
    ),
    Tool(
        name="list_beneficiaries",
        description="List all saved beneficiaries.",
        params=[],
        call=lambda api: api.get("/beneficiaries"),
        map_result=lambda data, args: {
            "beneficiary_summary": (
                "You have no beneficiaries on file."
                if not data else
                "Your beneficiaries are: " + ", ".join(
                    b.get("nickname") or b.get("email") for b in data
                )
            ),
        },
        success_template="{beneficiary_summary}",
        input_examples=[],
        category="banking",
    ),
    Tool(
        name="send_to_beneficiary",
        description="Send money to a saved beneficiary.",
        params=[
            Param("amount", type="number",
                  description="Amount to send in dollars",
                  prompt="the amount"),
            Param("from_account", type="string",
                  enum=["checking", "savings"],
                  description="Account to send from",
                  prompt="which account to send from"),
            Param("beneficiary_name", type="string",
                  description="Name or nickname of the beneficiary",
                  prompt="the beneficiary's name"),
        ],
        call=lambda api, amount, from_account, beneficiary_name: api.post(
            "/transactions",
            json={
                "type": "beneficiary_transfer",
                "amount": amount,
                "from_account_id": api.find_account_id(from_account),
                "beneficiary_id": api.find_beneficiary(beneficiary_name)["id"],
            },
        ),
        success_template="Done. Sent ${amount:.2f} to {beneficiary_name} from {from_account}.",
        error_template="Couldn't send to {beneficiary_name}: {error_message}.",
        input_examples=[
            {"amount": 50, "from_account": "checking", "beneficiary_name": "Alice"},
        ],
        category="banking",
    ),
    Tool(
        name="replace_card",
        description="Replace a damaged or lost card. A new card will be issued.",
        params=[
            Param("card_type", type="string",
                  enum=["credit", "debit"],
                  description="Type of card to replace",
                  prompt="credit or debit"),
            Param("card_last_four", type="string",
                  description="Last 4 digits of the card",
                  prompt="the last 4 digits"),
        ],
        call=lambda api, card_type, card_last_four: api.post(
            f"/cards/{api.find_card_id(card_type, card_last_four)}/replace",
        ),
        success_template="Done. A new {card_type} card will arrive in 5-7 business days.",
        error_template="Couldn't replace card: {error_message}.",
        input_examples=[{"card_type": "debit", "card_last_four": "1234"}],
        category="cards",
    ),
    Tool(
        name="activate_card",
        description="Activate a newly issued card.",
        params=[
            Param("card_last_four", type="string",
                  description="Last 4 digits of the card to activate",
                  prompt="the last 4 digits of the card"),
        ],
        call=lambda api, card_last_four: api.post(
            f"/cards/{api.find_card_id(None, card_last_four)}/activate",
        ),
        success_template="Your card ending in {card_last_four} is now active.",
        error_template="Couldn't activate card: {error_message}.",
        input_examples=[{"card_last_four": "1234"}],
        category="cards",
    ),
    Tool(
        name="reset_pin",
        description="Reset the PIN for a bank card.",
        params=[
            Param("card_type", type="string",
                  enum=["credit", "debit"],
                  description="Type of card",
                  prompt="credit or debit"),
            Param("card_last_four", type="string",
                  description="Last 4 digits of the card",
                  prompt="the last 4 digits"),
        ],
        call=lambda api, card_type, card_last_four: api.post(
            f"/cards/{api.find_card_id(card_type, card_last_four)}/reset-pin",
        ),
        success_template="Your PIN has been reset. You'll receive a new PIN by mail in 3-5 days.",
        error_template="Couldn't reset PIN: {error_message}.",
        input_examples=[{"card_type": "debit", "card_last_four": "1234"}],
        category="cards",
    ),
    Tool(
        name="report_fraud",
        description="Report suspected fraud on a card.",
        params=[
            Param("card_type", type="string",
                  enum=["credit", "debit"],
                  description="Type of card with suspected fraud",
                  prompt="credit or debit"),
            Param("card_last_four", type="string",
                  description="Last 4 digits of the card",
                  prompt="the last 4 digits",
                  required=False),
            Param("transaction_amount", type="number",
                  description="Amount of the suspicious transaction",
                  prompt="the transaction amount",
                  required=False),
        ],
        call=lambda api, card_type, card_last_four=None, transaction_amount=None: api.post(
            f"/cards/{api.find_card_id(card_type, card_last_four)}/fraud-reports",
            json={"transaction_amount": transaction_amount},
        ),
        success_template="I've flagged your {card_type} card for review. Our fraud team will contact you within 24 hours.",
        error_template="Couldn't report fraud: {error_message}.",
        input_examples=[{"card_type": "credit", "card_last_four": "1234", "transaction_amount": 50}],
        category="cards",
    ),
    Tool(
        name="get_statement",
        description="Request an account statement.",
        params=[
            Param("account_type", type="string",
                  enum=["checking", "savings", "credit"],
                  description="Type of account",
                  prompt="the account type (checking, savings, or credit)"),
            Param("period", type="string",
                  enum=["last_month", "last_3_months", "last_year"],
                  description="Time period for the statement",
                  required=False),
        ],
        call=lambda api, account_type, period="last_month": api.post(
            f"/accounts/{api.find_account_id(account_type)}/statement",
            json={"period": period},
        ),
        success_template="I'm sending your {account_type} statement to your registered email.",
        error_template="Couldn't get statement: {error_message}.",
        input_examples=[{"account_type": "checking"}],
        category="banking",
    ),
    Tool(
        name="add_beneficiary",
        description="Add a new beneficiary for money transfers.",
        params=[
            Param("email", type="string",
                  description="Email address of the beneficiary",
                  prompt="the beneficiary's email address"),
            Param("nickname", type="string",
                  description="Optional nickname for the beneficiary",
                  prompt="a nickname for this beneficiary",
                  required=False),
        ],
        call=lambda api, email, nickname=None: api.post(
            "/beneficiaries",
            json={"email": email, "nickname": nickname},
        ),
        map_result=lambda data, args: {"display_name": data.get("nickname") or data.get("email")},
        success_template="Done. Added {display_name} as a beneficiary.",
        error_template="Couldn't add beneficiary: {error_message}.",
        input_examples=[{"email": "alice@bankco.io", "nickname": "Alice"}],
        category="banking",
    ),
]

toolkit = Toolkit(
    tools=tools,
    api_factory=lambda auth_ctx: BankAPI(auth_ctx["token"]),
)
