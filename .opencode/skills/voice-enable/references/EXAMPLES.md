# Examples

## Banking — check_balance (simple read)

```python
Tool(
    name="check_balance",
    description="Check an account balance. Use when the user asks about "
                "their checking, savings, or credit balance.",
    params=[
        Param("account_type", type="string",
              enum=["checking", "savings", "credit"],
              description="Type of account", prompt="which account"),
    ],
    call=lambda api, account_type: api.get(
        "/accounts", params={"type": account_type}
    ),
    map_result=lambda data, args: {"balance": data[0]["balance"]},
    success_template="Your {account_type} balance is ${balance:.2f}.",
    error_template="Couldn't check {account_type}: {error_message}.",
    input_examples=[{"account_type": "checking"}],
    category="banking",
)
```

## E-commerce — track_order (simple read with composite response)

```python
Tool(
    name="track_order",
    description="Track an order by order number. Returns status and ETA. "
                "Use when user asks about an order they placed.",
    params=[
        Param("order_id", type="string",
              description="Order number (e.g. #1234)",
              prompt="your order number"),
    ],
    call=lambda api, order_id: api.get(f"/orders/{order_id}"),
    map_result=lambda data, args: {
        "status": data.get("status", "unknown"),
        "eta": data.get("estimated_delivery", "soon"),
    },
    success_template="Your order {order_id} is {status}. ETA: {eta}.",
    error_template="Couldn't find order {order_id}: {error_message}.",
    input_examples=[{"order_id": "ORD-1234"}],
    category="orders",
)
```

## SaaS — change_plan (simple write with find-then-act)

```python
Tool(
    name="change_plan",
    description="Change the user's subscription plan. Use when the user "
                "wants to upgrade or downgrade. Do not use for cancellation.",
    params=[
        Param("plan", type="string",
              enum=["free", "pro", "enterprise"],
              description="Target subscription plan",
              prompt="which plan you'd like"),
    ],
    call=lambda api, plan: api.post(
        "/subscription/plan", json={"plan": plan}
    ),
    success_template="Done. Your plan has been changed to {plan}.",
    error_template="Couldn't change plan: {error_message}.",
    input_examples=[{"plan": "pro"}],
    category="billing",
)
```

## Healthcare — book_appointment (multi-step: find + create)

```python
Tool(
    name="book_appointment",
    description="Book an appointment with a doctor. Use when the user "
                "wants to schedule a visit.",
    params=[
        Param("doctor", type="string",
              description="Doctor's name", prompt="which doctor"),
        Param("date", type="string",
              description="Preferred date (YYYY-MM-DD)", prompt="the date"),
        Param("time_slot", type="string",
              description="Time slot (e.g. 10:00 AM)",
              prompt="what time"),
    ],
    call=lambda api, doctor, date, time_slot: (
        lambda d_id: api.post(f"/doctors/{d_id}/appointments", json={
            "date": date, "time": time_slot
        })
    )(api.get("/doctors", params={"name": doctor})[0]["id"]),
    success_template="Booked with Dr. {doctor} on {date} at {time_slot}.",
    error_template="Couldn't book: {error_message}.",
    input_examples=[{"doctor": "Smith", "date": "2026-08-15", "time_slot": "10:00 AM"}],
    category="appointments",
)
```

## Pattern summary

| Pattern | Lambda structure |
|---------|-----------------|
| Simple read | `api.get(path, params=kwargs)` → `map_result` extracts |
| Simple write | `api.post(path, json=kwargs)` → ignore response |
| Find-then-act | `api.get(search_path)` → extract ID → `api.post(action_path, json=...)` |
| Composite | Multiple API calls, aggregated response |
| Void | Call API, return `{}`, template uses original args only |
