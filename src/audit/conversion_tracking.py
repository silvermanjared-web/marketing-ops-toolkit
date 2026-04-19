"""
Google Ads Conversion Tracking Audit.

Validates that conversion actions are properly configured and actively
receiving data. Catches common issues:
- Conversion actions included in the Conversions column that shouldn't be
- Stale actions with no recent data
- Misconfigured attribution models or counting types
- Missing offline conversion uploads

Usage:
    python -m src.audit.conversion_tracking
    python -m src.audit.conversion_tracking --config config/google-ads.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = "config/google-ads.yaml"
STALE_THRESHOLD_DAYS = 14  # No conversions in N days = stale


@dataclass
class ConversionFinding:
    """A single conversion tracking finding."""
    severity: str
    action_name: str
    check: str
    detail: str


@dataclass
class ConversionReport:
    """Aggregated conversion audit results."""
    account_name: str
    account_id: str
    total_actions: int
    active_actions: int
    findings: list[ConversionFinding] = field(default_factory=list)

    def add(self, severity: str, action_name: str, check: str,
            detail: str) -> None:
        self.findings.append(ConversionFinding(severity, action_name, check, detail))


# ── Google Ads client ────────────────────────────────────────────────────────

def load_client(config_path: str) -> tuple[GoogleAdsClient, str]:
    """Load Google Ads client and customer ID from YAML config."""
    path = Path(config_path)
    if not path.exists():
        print(f"Config not found: {path}")
        print("Copy config/google-ads.example.yaml to config/google-ads.yaml")
        sys.exit(1)

    with open(path) as f:
        config = yaml.safe_load(f)

    client = GoogleAdsClient.load_from_dict({
        "developer_token": config["developer_token"],
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": config["refresh_token"],
        "login_customer_id": config.get("login_customer_id", ""),
        "use_proto_plus": config.get("use_proto_plus", True),
    })

    customer_id = config.get("customer_id", config.get("login_customer_id", ""))
    return client, str(customer_id).replace("-", "")


def run_query(client: GoogleAdsClient, customer_id: str, query: str) -> list:
    """Execute a GAQL query and return all result rows."""
    service = client.get_service("GoogleAdsService")
    rows = []
    try:
        response = service.search_stream(customer_id=customer_id, query=query)
        for batch in response:
            rows.extend(batch.results)
    except Exception as e:
        print(f"  Query error: {e}")
    return rows


# ── Data pull ────────────────────────────────────────────────────────────────

def pull_account_info(client: GoogleAdsClient, customer_id: str) -> dict:
    """Pull basic account metadata."""
    query = """
        SELECT customer.descriptive_name, customer.id
        FROM customer LIMIT 1
    """
    rows = run_query(client, customer_id, query)
    if rows:
        return {
            "name": rows[0].customer.descriptive_name,
            "id": str(rows[0].customer.id),
        }
    return {"name": "Unknown", "id": customer_id}


def pull_conversion_actions(client: GoogleAdsClient,
                            customer_id: str) -> list[dict]:
    """Pull all conversion action configurations."""
    query = """
        SELECT conversion_action.id, conversion_action.name,
               conversion_action.type, conversion_action.status,
               conversion_action.category,
               conversion_action.attribution_model_settings.attribution_model,
               conversion_action.counting_type,
               conversion_action.include_in_conversions_metric,
               conversion_action.value_settings.default_value,
               conversion_action.click_through_lookback_window_days,
               conversion_action.view_through_lookback_window_days
        FROM conversion_action
        ORDER BY conversion_action.id
    """
    rows = run_query(client, customer_id, query)
    actions = []
    for r in rows:
        ca = r.conversion_action
        actions.append({
            "id": ca.id,
            "name": ca.name,
            "type": ca.type_.name,
            "status": ca.status.name,
            "category": ca.category.name,
            "attribution_model": (
                ca.attribution_model_settings.attribution_model.name
                if ca.attribution_model_settings else "N/A"
            ),
            "counting": ca.counting_type.name,
            "include_in_conversions": ca.include_in_conversions_metric,
            "default_value": (
                ca.value_settings.default_value
                if ca.value_settings else 0
            ),
            "click_lookback": ca.click_through_lookback_window_days,
            "view_lookback": ca.view_through_lookback_window_days,
        })
    return actions


def pull_conversion_performance(client: GoogleAdsClient,
                                customer_id: str,
                                days: int = 30) -> dict[str, float]:
    """Pull recent conversion counts by action name.

    Returns a mapping of conversion action name to total conversions
    in the lookback period.
    """
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT conversion_action.name,
               metrics.all_conversions
        FROM conversion_action
        WHERE segments.date BETWEEN '{start}' AND '{end}'
    """
    rows = run_query(client, customer_id, query)
    perf: dict[str, float] = {}
    for r in rows:
        name = r.conversion_action.name
        perf[name] = perf.get(name, 0) + r.metrics.all_conversions
    return perf


# ── Audit checks ─────────────────────────────────────────────────────────────

def check_signal_contamination(actions: list[dict],
                               report: ConversionReport) -> None:
    """Flag conversion actions included in the Conversions column that
    look like noise (app installs, micro-conversions, page views).

    Smart Bidding optimizes toward whatever is in the Conversions column.
    Including irrelevant actions distorts bid optimization.
    """
    noise_types = {"GOOGLE_PLAY_DOWNLOAD", "GOOGLE_PLAY_IN_APP_PURCHASE",
                   "ANDROID_APP_PRE_REGISTRATION"}
    noise_categories = {"DOWNLOAD", "PAGE_VIEW", "ADD_TO_CART"}

    for a in actions:
        if not a["include_in_conversions"]:
            continue

        if a["type"] in noise_types:
            report.add(
                "CRITICAL", a["name"], "signal_contamination",
                f"Action type '{a['type']}' is included in the Conversions "
                f"column. Smart Bidding may optimize toward irrelevant "
                f"app installs instead of actual leads/sales.",
            )
        elif a["category"] in noise_categories:
            report.add(
                "WARNING", a["name"], "signal_contamination",
                f"Category '{a['category']}' is included in the Conversions "
                f"column. Consider whether this micro-conversion should "
                f"influence bid optimization.",
            )


def check_stale_actions(actions: list[dict],
                        recent_performance: dict[str, float],
                        report: ConversionReport) -> None:
    """Flag enabled conversion actions with no recent data."""
    for a in actions:
        if a["status"] != "ENABLED":
            continue

        recent_count = recent_performance.get(a["name"], 0)
        if recent_count == 0:
            report.add(
                "WARNING", a["name"], "stale_action",
                f"Enabled conversion action with 0 conversions in the last "
                f"{STALE_THRESHOLD_DAYS} days. Tracking may be broken, "
                f"or this action is no longer relevant.",
            )


def check_attribution_models(actions: list[dict],
                             report: ConversionReport) -> None:
    """Flag actions using last-click attribution (suboptimal for
    multi-touch journeys)."""
    for a in actions:
        if a["status"] != "ENABLED" or not a["include_in_conversions"]:
            continue

        if a["attribution_model"] == "GOOGLE_ADS_LAST_CLICK":
            report.add(
                "INFO", a["name"], "attribution_model",
                f"Using last-click attribution. Consider data-driven "
                f"attribution for better cross-campaign credit assignment.",
            )


def check_counting_type(actions: list[dict],
                        report: ConversionReport) -> None:
    """Flag lead-type conversions using 'every' counting (should be 'one')."""
    lead_categories = {"SUBMIT_LEAD_FORM", "SIGNUP", "CONTACT", "REQUEST_QUOTE",
                       "BOOK_APPOINTMENT", "GET_DIRECTIONS", "PHONE_CALL_LEAD"}

    for a in actions:
        if a["status"] != "ENABLED":
            continue

        if a["category"] in lead_categories and a["counting"] == "MANY_PER_CLICK":
            report.add(
                "WARNING", a["name"], "counting_type",
                f"Lead-type action ('{a['category']}') is set to count "
                f"every conversion. For leads, 'one per click' prevents "
                f"duplicate counting from page refreshes.",
            )


def check_offline_upload_health(actions: list[dict],
                                recent_performance: dict[str, float],
                                report: ConversionReport) -> None:
    """Flag offline conversion actions that may have upload issues."""
    offline_types = {"UPLOAD_CALLS", "UPLOAD_CLICKS", "STORE_SALES_DIRECT_UPLOAD"}

    for a in actions:
        if a["type"] not in offline_types or a["status"] != "ENABLED":
            continue

        recent_count = recent_performance.get(a["name"], 0)
        if recent_count == 0:
            report.add(
                "CRITICAL", a["name"], "offline_upload",
                f"Offline conversion action ({a['type']}) has 0 conversions "
                f"recently. Upload pipeline may be broken — check your CRM "
                f"integration or upload schedule.",
            )


def check_lookback_windows(actions: list[dict],
                           report: ConversionReport) -> None:
    """Flag unusually short lookback windows."""
    for a in actions:
        if a["status"] != "ENABLED" or not a["include_in_conversions"]:
            continue

        if a["click_lookback"] and a["click_lookback"] < 30:
            report.add(
                "INFO", a["name"], "short_lookback",
                f"Click-through lookback is {a['click_lookback']} days. "
                f"For long consideration cycles (B2B, education, real estate), "
                f"consider 60-90 days to capture delayed conversions.",
            )


# ── Report output ────────────────────────────────────────────────────────────

def print_report(report: ConversionReport) -> None:
    """Print formatted conversion tracking audit."""
    print("\n" + "=" * 72)
    print("  CONVERSION TRACKING AUDIT")
    print("=" * 72)
    print(f"  Account:          {report.account_name} ({report.account_id})")
    print(f"  Total actions:    {report.total_actions}")
    print(f"  Active actions:   {report.active_actions}")
    print(f"  Findings:         {len(report.findings)}")
    print("=" * 72)

    if not report.findings:
        print("\n  Conversion tracking looks healthy. No issues found.\n")
        return

    for severity in ("CRITICAL", "WARNING", "INFO"):
        findings = [f for f in report.findings if f.severity == severity]
        if not findings:
            continue

        marker = {"CRITICAL": "!!!", "WARNING": " ! ", "INFO": " i "}[severity]
        print(f"\n  [{marker}] {severity} ({len(findings)})")
        print("  " + "-" * 68)

        for f in findings:
            print(f"  Action:  {f.action_name}")
            print(f"  Check:   {f.check}")
            print(f"  Detail:  {f.detail}")
            print()


# ── Main ─────────────────────────────────────────────────────────────────────

def run_audit(config_path: str = DEFAULT_CONFIG_PATH) -> ConversionReport:
    """Run the full conversion tracking audit."""
    client, customer_id = load_client(config_path)

    print(f"Auditing conversion tracking for customer {customer_id}...")

    account_info = pull_account_info(client, customer_id)
    actions = pull_conversion_actions(client, customer_id)
    recent_perf = pull_conversion_performance(client, customer_id,
                                              days=STALE_THRESHOLD_DAYS)

    active_actions = [a for a in actions if a["status"] == "ENABLED"]
    print(f"  Found {len(actions)} conversion actions ({len(active_actions)} active)")

    report = ConversionReport(
        account_name=account_info["name"],
        account_id=account_info["id"],
        total_actions=len(actions),
        active_actions=len(active_actions),
    )

    check_signal_contamination(actions, report)
    check_stale_actions(actions, recent_perf, report)
    check_attribution_models(actions, report)
    check_counting_type(actions, report)
    check_offline_upload_health(actions, recent_perf, report)
    check_lookback_windows(actions, report)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Ads conversion tracking audit"
    )
    parser.add_argument(
        "--config", type=str, default=DEFAULT_CONFIG_PATH,
        help=f"Path to google-ads.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args()

    report = run_audit(config_path=args.config)
    print_report(report)


if __name__ == "__main__":
    main()
