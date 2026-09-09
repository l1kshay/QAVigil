"""Loads the externalized test data.

Why a module and not a fixture: ``@pytest.mark.parametrize`` needs its cases at
*collection* time, before any fixture has run. A fixture-based loader would
force every data-driven test into a loop inside one test function, which
collapses a dozen independent cases into a single pass/fail. Loading at import
time keeps one test per data record, which is what makes a report readable.

Results are cached, so a file is parsed once per session however many test
modules ask for it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_yaml(filename: str) -> dict[str, Any]:
    """Parse a YAML file from test_data/."""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"test data file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=None)
def load_json(filename: str) -> dict[str, Any]:
    """Parse a JSON file from test_data/."""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"test data file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# ----------------------------------------------------------------------
# named accessors - one per data file
# ----------------------------------------------------------------------
def users() -> dict[str, Any]:
    return load_yaml("users.yaml")


def products() -> dict[str, Any]:
    return load_json("products.json")


def edge_cases() -> dict[str, Any]:
    return load_yaml("edge_cases.yaml")


def checkout() -> dict[str, Any]:
    return load_yaml("checkout.yaml")


def case_ids(records: list[dict[str, Any]]) -> list[str]:
    """Pull the ``id`` field out of each record, for pytest's test ids.

    Without this, parametrized cases show up as ``case0``, ``case1`` in the
    report; with it they show up as ``unknown-email``, ``wrong-password``,
    which is the difference between a report you can read and one you cannot.
    """
    return [record["id"] for record in records]
