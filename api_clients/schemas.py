"""JSON Schemas describing the target API's response contracts.

These live beside the clients rather than in test_data/ because they are not
test *inputs* - they are the contract the API is expected to honour, and they
belong to the client layer that speaks to it.

Every schema was derived from live responses (verified 2026-09-09), not from
the site's prose documentation, so they describe what the API actually sends.

A note on ``price``: the API returns it as a display string ("Rs. 500"), not a
number. The schema says ``string`` deliberately - tightening it to a number
would be asserting what we wish were true rather than what is.
"""

from __future__ import annotations

from typing import Any

#: Every response carries this envelope, whatever else it contains.
ENVELOPE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode"],
    "properties": {"responseCode": {"type": "integer"}},
}

#: Responses whose entire payload is a status and a human-readable message.
MESSAGE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode", "message"],
    "properties": {
        "responseCode": {"type": "integer"},
        "message": {"type": "string", "minLength": 1},
    },
}

_CATEGORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["category", "usertype"],
    "properties": {
        "category": {"type": "string"},
        "usertype": {
            "type": "object",
            "required": ["usertype"],
            "properties": {"usertype": {"type": "string"}},
        },
    },
}

_PRODUCT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name", "price", "brand", "category"],
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string", "minLength": 1},
        # Display string such as "Rs. 500" - see the module docstring.
        "price": {"type": "string", "minLength": 1},
        "brand": {"type": "string"},
        "category": _CATEGORY_SCHEMA,
    },
}

PRODUCTS_LIST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode", "products"],
    "properties": {
        "responseCode": {"type": "integer"},
        "products": {"type": "array", "minItems": 1, "items": _PRODUCT_SCHEMA},
    },
}

#: A search may legitimately match nothing, so no minItems here.
SEARCH_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode", "products"],
    "properties": {
        "responseCode": {"type": "integer"},
        "products": {"type": "array", "items": _PRODUCT_SCHEMA},
    },
}

BRANDS_LIST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode", "brands"],
    "properties": {
        "responseCode": {"type": "integer"},
        "brands": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "brand"],
                "properties": {
                    "id": {"type": "integer"},
                    "brand": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

USER_DETAIL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["responseCode", "user"],
    "properties": {
        "responseCode": {"type": "integer"},
        "user": {
            "type": "object",
            "required": ["id", "name", "email", "first_name", "last_name"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "title": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "company": {"type": "string"},
                "address1": {"type": "string"},
                "address2": {"type": "string"},
                "country": {"type": "string"},
                "state": {"type": "string"},
                "city": {"type": "string"},
                "zipcode": {"type": "string"},
                # The API returns these as strings, and names the day field
                # birth_day on the way out even though createAccount takes it
                # as birth_date on the way in.
                "birth_day": {"type": "string"},
                "birth_month": {"type": "string"},
                "birth_year": {"type": "string"},
            },
        },
    },
}
