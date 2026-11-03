"""JSON schemas of the tools exposed to the LLM (OpenAI function-calling format).

The descriptions are part of the prompt: they tell the model *when* each tool is the right one, which
is the "data vs policies" routing the challenge asks for.
"""


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


def build_schemas(category_names: list[str]) -> list[dict]:
    contact = {
        "type": "string",
        "description": "E-mail or phone number the customer says is registered on the order. "
        "Not needed again once the customer was verified in this conversation.",
    }
    return [
        _tool(
            "search_products",
            "Search the instrument catalog by keywords, category and/or price. Use for any question "
            "about what the store sells, availability, options or price ranges. Returns current "
            "prices (with promotions applied), availability and stock.",
            {
                "keywords": {
                    "type": "string",
                    "description": "Brand, model, type or color only (e.g. 'Yamaha nylon'). "
                    "Do not put prices or filler words here.",
                },
                "category": {"type": "string", "enum": category_names},
                "max_price": {"type": "number", "description": "Highest price in BRL the customer will pay."},
                "min_price": {"type": "number"},
                "only_available": {
                    "type": "boolean",
                    "description": "Default true: hide discontinued and out-of-stock items.",
                },
            },
        ),
        _tool(
            "get_product",
            "Full details of ONE product: price, promotion, PIX price, installments, stock, "
            "specs, special freight and alternatives if it is unavailable. Use for 'how much is X', "
            "'do you have X', or details about a specific model. Accepts a product name or id.",
            {"product": {"type": "string", "description": "Product name (any recognizable part) or id."}},
            ["product"],
        ),
        _tool(
            "get_store_info",
            "Store address, phone/WhatsApp, e-mail, opening hours, what the store sells, and whether it "
            "is open right now (with the next opening time). Use for 'where', 'what time', 'are you open'.",
            {},
        ),
        _tool(
            "get_order_status",
            "Status, items, total, tracking code and delivery estimate of an order. The customer must "
            "give the order number AND the e-mail or phone registered on the order; never call this "
            "without both unless the order was already verified in this conversation.",
            {"order_id": {"type": "integer"}, "contact": contact},
            ["order_id"],
        ),
        _tool(
            "check_return_eligibility",
            "Decide whether an order can be returned or exchanged today, applying the store's return, "
            "exchange and warranty rules to the order's dates. Use for 'I want to return', 'it arrived "
            "broken', 'I want to swap it'. Same verification as get_order_status.",
            {
                "order_id": {"type": "integer"},
                "reason": {
                    "type": "string",
                    "enum": ["regret", "defect", "preference"],
                    "description": "regret = changed their mind; defect = manufacturing defect; "
                    "preference = wants another color/model.",
                },
                "contact": contact,
            },
            ["order_id", "reason"],
        ),
        _tool(
            "calculate_payment_options",
            "Installment options (credit card), PIX/boleto notes and whether payment methods can be "
            "combined, for a given amount. Use for questions about paying in installments.",
            {"amount": {"type": "number", "description": "Purchase amount in BRL."}},
            ["amount"],
        ),
        _tool(
            "estimate_shipping",
            "Shipping cost and delivery time for a purchase. Free/flat rate inside the Campo Grande "
            "metro area; other cities need a CEP quote.",
            {
                "order_total": {"type": "number", "description": "Purchase total in BRL."},
                "city": {"type": "string"},
                "product": {"type": "string", "description": "Optional product name, to detect large items."},
            },
            ["order_total", "city"],
        ),
        _tool(
            "search_policies",
            "Search the store's policies manual (returns, exchanges, warranty, payment rules, "
            "promotions, privacy, complaints, service guidelines, shipping rules). Use for any 'what is "
            "the rule' question that is not about a specific order or product price.",
            {"query": {"type": "string", "description": "The customer's question in Portuguese."}},
            ["query"],
        ),
        _tool(
            "escalate_to_human",
            "Hand the conversation to a human agent: complaints, exceptions, warranty claims, anything "
            "the rules do not cover, or when a tool says a human is needed. Returns a ticket number and "
            "the response time to tell the customer.",
            {
                "kind": {"type": "string", "enum": ["complaint", "return_or_warranty", "order_issue", "other"]},
                "summary": {"type": "string", "description": "What the customer needs, in one or two sentences."},
                "order_id": {"type": "integer"},
                "customer_contact": {"type": "string", "description": "Name/phone/e-mail the customer gave."},
            },
            ["kind", "summary"],
        ),
    ]
