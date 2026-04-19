"""
Rule engine for Gmail inbox automation.

Rules are loaded from a JSON config file or defined inline. Each rule specifies
a Gmail search query, a target label, and actions (archive, mark read).

Config format (gmail_rules.json):
[
    {
        "name": "Receipts - transactional",
        "query": "from:(receipts@store.example.com OR noreply@shop.example.com) in:inbox",
        "label": "INBOX/RECEIPTS",
        "archive": true,
        "mark_read": false
    },
    ...
]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Rule:
    """A single inbox processing rule."""
    name: str
    query: str
    label: str
    archive: bool = True
    mark_read: bool = False

    def __str__(self) -> str:
        actions = []
        if self.label:
            actions.append(f"label:{self.label}")
        if self.archive:
            actions.append("archive")
        if self.mark_read:
            actions.append("mark_read")
        return f"Rule({self.name!r}, {' + '.join(actions)})"


def load_rules(config_path: str | Path) -> list[Rule]:
    """Load rules from a JSON config file.

    Args:
        config_path: Path to the JSON rules file.

    Returns:
        List of Rule objects, validated and ready for processing.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If a rule is missing required fields.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Rules config not found: {path}")

    with open(path) as f:
        raw_rules = json.load(f)

    rules = []
    for i, entry in enumerate(raw_rules):
        _validate_rule_entry(entry, index=i)
        rules.append(Rule(
            name=entry["name"],
            query=entry["query"],
            label=entry["label"],
            archive=entry.get("archive", True),
            mark_read=entry.get("mark_read", False),
        ))

    return rules


def _validate_rule_entry(entry: dict, index: int) -> None:
    """Validate a single rule entry from config."""
    required = ("name", "query", "label")
    for field in required:
        if field not in entry:
            raise ValueError(f"Rule at index {index} missing required field: {field!r}")

    if not entry["query"].strip():
        raise ValueError(f"Rule at index {index} ({entry['name']!r}) has empty query")


# ── Default rules (used when no config file is provided) ─────────────────────

DEFAULT_RULES: list[Rule] = [
    Rule(
        name="Intel - industry newsletters",
        query=(
            "from:(digest@industry.example.com OR "
            "newsletter@martech.example.com OR "
            "weekly@analytics.example.com) in:inbox"
        ),
        label="INBOX/INTEL",
        archive=True,
        mark_read=False,
    ),
    Rule(
        name="Receipts - transactional emails",
        query=(
            'subject:("your receipt" OR "order confirmation" OR '
            '"payment received" OR "payment successful") in:inbox'
        ),
        label="INBOX/RECEIPTS",
        archive=True,
        mark_read=False,
    ),
    Rule(
        name="Receipts - shipping notifications",
        query=(
            'subject:("has shipped" OR "out for delivery" OR '
            '"package delivered" OR "tracking number") in:inbox'
        ),
        label="INBOX/RECEIPTS",
        archive=True,
        mark_read=True,
    ),
    Rule(
        name="Notifications - calendar and system",
        query=(
            "from:(calendar-notification@google.com OR "
            "noreply@alerts.example.com OR "
            "notifications@system.example.com) in:inbox"
        ),
        label="INBOX/NOTIFICATIONS",
        archive=True,
        mark_read=True,
    ),
    Rule(
        name="Promotions - known marketing senders",
        query=(
            "from:(deals@retailer.example.com OR "
            "offers@brand.example.com OR "
            "promo@store.example.com) in:inbox"
        ),
        label="INBOX/PROMOTIONS",
        archive=True,
        mark_read=True,
    ),
    Rule(
        name="Promotions - alias catch-all",
        query="to:alias@example.com in:inbox",
        label="INBOX/PROMOTIONS",
        archive=True,
        mark_read=True,
    ),
]


def get_rules(config_path: Optional[str | Path] = None) -> list[Rule]:
    """Get rules from config file if provided, otherwise use defaults.

    Args:
        config_path: Optional path to JSON rules config. If None, returns
                     built-in default rules.

    Returns:
        List of Rule objects.
    """
    if config_path is not None:
        return load_rules(config_path)
    return list(DEFAULT_RULES)
