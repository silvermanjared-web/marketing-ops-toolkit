"""
Gmail Inbox Accelerator — rule-based batch email processing.

Applies configurable rules to categorize, label, archive, and mark-read
Gmail messages. Processes up to 1,000 messages per API call using
batchModify. Maintains state across runs so it can resume where it left off.

Usage:
    python -m src.inbox.accelerator              # Process inbox
    python -m src.inbox.accelerator --dry        # Preview changes (no writes)
    python -m src.inbox.accelerator --status     # Print current state
    python -m src.inbox.accelerator --reset      # Reset state to start over
    python -m src.inbox.accelerator --config config/gmail_rules.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.inbox.rules import Rule, get_rules

# ── Constants ────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
STATE_FILE = "state.json"
BATCH_SIZE = 1000          # Gmail batchModify limit
MAX_RUNTIME_SEC = 270      # 4.5 minutes — safe margin for cron/scheduler
MAX_CONSECUTIVE_ERRORS = 5


# ── Authentication ───────────────────────────────────────────────────────────

def get_gmail_service(credentials_file: str = "credentials.json",
                      token_file: str = "token.json"):
    """Authenticate and return a Gmail API service instance.

    Uses OAuth2 with offline access. Refreshes expired tokens automatically.
    On first run, opens a browser for consent.
    """
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── State management ─────────────────────────────────────────────────────────

def load_state(state_file: str = STATE_FILE) -> dict:
    """Load processing state from disk. Returns fresh state if none exists."""
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {
        "phase": "processing",
        "rule_index": 0,
        "labeled": 0,
        "archived": 0,
        "errors": 0,
        "runs": 0,
        "last_run": None,
    }


def save_state(state: dict, state_file: str = STATE_FILE) -> None:
    """Persist state to disk."""
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


# ── Gmail operations ─────────────────────────────────────────────────────────

def get_or_create_label(service, label_name: str) -> str:
    """Return the Gmail label ID for the given name, creating it if needed.

    Gmail labels are hierarchical — "INBOX/RECEIPTS" creates a nested label.
    """
    result = service.users().labels().list(userId="me").execute()
    for label in result.get("labels", []):
        if label["name"] == label_name:
            return label["id"]

    created = service.users().labels().create(
        userId="me",
        body={
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    print(f"  Created label: {label_name}")
    return created["id"]


def search_messages(service, query: str, max_results: int = BATCH_SIZE) -> list[str]:
    """Return up to max_results message IDs matching a Gmail search query.

    Paginates through results, respecting the Gmail API's 500-per-page limit.
    """
    message_ids: list[str] = []
    page_token = None

    while len(message_ids) < max_results:
        params = {
            "userId": "me",
            "q": query,
            "maxResults": min(max_results - len(message_ids), 500),
        }
        if page_token:
            params["pageToken"] = page_token

        response = service.users().messages().list(**params).execute()
        message_ids.extend(m["id"] for m in response.get("messages", []))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return message_ids


def apply_rule_batch(service, message_ids: list[str], label_id: str,
                     rule: Rule) -> None:
    """Apply a rule to up to 1,000 messages in a single API call.

    Uses Gmail's batchModify endpoint — one HTTP request regardless of
    how many messages are being modified.
    """
    add_labels = [label_id]
    remove_labels: list[str] = []

    if rule.mark_read:
        remove_labels.append("UNREAD")
    if rule.archive:
        remove_labels.append("INBOX")

    service.users().messages().batchModify(
        userId="me",
        body={
            "ids": message_ids,
            "addLabelIds": add_labels,
            "removeLabelIds": remove_labels,
        },
    ).execute()


# ── Main processing loop ─────────────────────────────────────────────────────

def run_accelerator(rules: list[Rule], dry_run: bool = False) -> None:
    """Process inbox rules in order, batching modifications.

    State machine:
        - Iterates through rules sequentially
        - For each rule, searches for matching messages and applies actions
        - If a rule matches messages, re-runs it until exhausted (handles
          inboxes with >1,000 matching messages per rule)
        - Saves state after each batch so processing resumes on next run
        - Stops after MAX_RUNTIME_SEC to stay within scheduler limits
    """
    service = get_gmail_service()
    state = load_state()
    start_time = time.time()

    state["runs"] += 1
    run_num = state["runs"]

    print(
        f"Run #{run_num} | phase={state['phase']} | "
        f"rule={state['rule_index']}/{len(rules) - 1} | "
        f"labeled={state['labeled']} | archived={state['archived']}"
    )

    if state["phase"] == "done":
        print("All rules processed. Nothing to do. Use --reset to start over.")
        save_state(state)
        return

    label_id_cache: dict[str, str] = {}
    consecutive_errors = 0

    while (time.time() - start_time) < MAX_RUNTIME_SEC:
        idx = state["rule_index"]

        if idx >= len(rules):
            state["phase"] = "done"
            print(f"All {len(rules)} rules processed. Marking done.")
            break

        rule = rules[idx]

        # Search for matching messages
        try:
            message_ids = search_messages(service, rule.query, BATCH_SIZE)
        except HttpError as e:
            consecutive_errors += 1
            state["errors"] += 1
            print(f"Search error on rule {idx} ({rule.name}): {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print("Too many consecutive errors — aborting run.")
                break
            time.sleep(2)
            continue

        # No matches — rule exhausted, move to next
        if not message_ids:
            print(f"Rule {idx} ({rule.name}): no matches, advancing.")
            state["rule_index"] += 1
            consecutive_errors = 0
            save_state(state)
            continue

        # Dry run — report what would happen
        if dry_run:
            print(
                f"[DRY RUN] Rule {idx} ({rule.name}): "
                f"would process {len(message_ids)} messages"
            )
            state["rule_index"] += 1
            consecutive_errors = 0
            save_state(state)
            continue

        # Apply the rule
        try:
            label_name = rule.label
            if label_name not in label_id_cache:
                label_id_cache[label_name] = get_or_create_label(service, label_name)
            label_id = label_id_cache[label_name]

            apply_rule_batch(service, message_ids, label_id, rule)

            state["labeled"] += len(message_ids)
            if rule.archive:
                state["archived"] += len(message_ids)

            print(
                f"Rule {idx} ({rule.name}): processed {len(message_ids)} "
                f"messages in 1 API call | total labeled={state['labeled']}"
            )
            consecutive_errors = 0

        except HttpError as e:
            consecutive_errors += 1
            state["errors"] += 1
            print(f"Processing error on rule {idx} ({rule.name}): {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print("Too many consecutive errors — aborting run.")
                break
            time.sleep(2)

        save_state(state)

    # Finalize
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    elapsed = round(time.time() - start_time)
    print(
        f"Run #{run_num} complete | {elapsed}s | "
        f"labeled={state['labeled']} | archived={state['archived']} | "
        f"errors={state['errors']} | next_rule={state['rule_index']}"
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def print_status() -> None:
    """Print current processing state."""
    state = load_state()
    print("=== Inbox Accelerator Status ===")
    print(f"Phase:      {state.get('phase', 'not started')}")
    print(f"Rule index: {state.get('rule_index', 0)}")
    print(f"Labeled:    {state.get('labeled', 0)}")
    print(f"Archived:   {state.get('archived', 0)}")
    print(f"Errors:     {state.get('errors', 0)}")
    print(f"Runs:       {state.get('runs', 0)}")
    print(f"Last run:   {state.get('last_run', 'never')}")


def reset_state() -> None:
    """Delete state file to start fresh."""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print("State reset. Next run will start from rule 0.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gmail Inbox Accelerator — batch rule-based email processing"
    )
    parser.add_argument(
        "--dry", action="store_true",
        help="Dry run — preview what would change without modifying anything",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print current processing state and exit",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset state to start over from rule 0",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to JSON rules config (default: use built-in rules)",
    )
    args = parser.parse_args()

    if args.status:
        print_status()
        sys.exit(0)

    if args.reset:
        reset_state()
        sys.exit(0)

    rules = get_rules(args.config)
    print(f"Loaded {len(rules)} rules")
    run_accelerator(rules, dry_run=args.dry)


if __name__ == "__main__":
    main()
