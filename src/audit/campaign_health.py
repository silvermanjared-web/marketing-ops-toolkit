"""
Google Ads Campaign Health Audit.

Queries campaign performance data via GAQL and runs structural health checks:
- Budget pacing (spend vs. daily budget utilization)
- Conversion volume and cost-per-conversion trends
- Naming convention compliance
- Impression share and lost opportunity analysis
- Campaign status anomalies

Usage:
    python -m src.audit.campaign_health
    python -m src.audit.campaign_health --config config/google-ads.yaml
    python -m src.audit.campaign_health --days 60
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = "config/google-ads.yaml"
DEFAULT_LOOKBACK_DAYS = 30

# Naming convention: {channel}_{geo}_{audience}_{objective}
# Example: search_us_remarketing_leads, pmax_ca_prospecting_sales
NAMING_PATTERN = re.compile(
    r"^(search|pmax|display|video|discovery|demand_gen|shopping)"
    r"_[a-z]{2,}"
    r"_[a-z]+"
    r"_[a-z]+",
    re.IGNORECASE,
)

# Thresholds
BUDGET_UNDERSPEND_THRESHOLD = 0.70    # <70% utilization = flagged
BUDGET_OVERSPEND_THRESHOLD = 1.10     # >110% utilization = flagged
HIGH_CPA_MULTIPLIER = 2.0            # >2x account avg = flagged
LOW_IMPRESSION_SHARE = 0.30          # <30% IS = flagged
HIGH_BUDGET_LOST_IS = 0.20           # >20% budget-lost IS = flagged


@dataclass
class Finding:
    """A single audit finding."""
    severity: str     # CRITICAL, WARNING, INFO
    campaign: str
    check: str
    detail: str


@dataclass
class AuditReport:
    """Aggregated audit results."""
    account_name: str
    account_id: str
    lookback_days: int
    campaigns_checked: int
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, campaign: str, check: str, detail: str) -> None:
        self.findings.append(Finding(severity, campaign, check, detail))

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARNING")


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
        SELECT customer.descriptive_name, customer.id,
               customer.currency_code, customer.auto_tagging_enabled
        FROM customer
        LIMIT 1
    """
    rows = run_query(client, customer_id, query)
    if rows:
        r = rows[0]
        return {
            "name": r.customer.descriptive_name,
            "id": str(r.customer.id),
            "currency": r.customer.currency_code,
            "auto_tagging": r.customer.auto_tagging_enabled,
        }
    return {"name": "Unknown", "id": customer_id, "currency": "USD", "auto_tagging": False}


def pull_campaign_performance(client: GoogleAdsClient, customer_id: str,
                              days: int) -> list[dict]:
    """Pull campaign-level performance for the lookback window."""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type,
               campaign.bidding_strategy_type,
               campaign_budget.amount_micros,
               metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.conversions_value,
               metrics.ctr, metrics.average_cpc, metrics.cost_per_conversion,
               metrics.search_impression_share,
               metrics.search_budget_lost_impression_share,
               metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """
    rows = run_query(client, customer_id, query)
    campaigns = []
    for r in rows:
        cost = r.metrics.cost_micros / 1_000_000
        clicks = r.metrics.clicks
        conversions = r.metrics.conversions
        daily_budget = r.campaign_budget.amount_micros / 1_000_000

        campaigns.append({
            "id": r.campaign.id,
            "name": r.campaign.name,
            "status": r.campaign.status.name,
            "channel": r.campaign.advertising_channel_type.name,
            "bidding": r.campaign.bidding_strategy_type.name,
            "daily_budget": daily_budget,
            "cost": cost,
            "impressions": r.metrics.impressions,
            "clicks": clicks,
            "conversions": conversions,
            "conv_value": r.metrics.conversions_value,
            "ctr": r.metrics.ctr,
            "avg_cpc": r.metrics.average_cpc / 1_000_000 if r.metrics.average_cpc else 0,
            "cpa": r.metrics.cost_per_conversion / 1_000_000 if r.metrics.cost_per_conversion else 0,
            "search_is": r.metrics.search_impression_share,
            "budget_lost_is": r.metrics.search_budget_lost_impression_share,
            "rank_lost_is": r.metrics.search_rank_lost_impression_share,
            "daily_spend_avg": cost / days if days > 0 else 0,
        })
    return campaigns


# ── Audit checks ─────────────────────────────────────────────────────────────

def check_budget_pacing(campaigns: list[dict], report: AuditReport,
                        days: int) -> None:
    """Flag campaigns that are significantly over- or under-spending."""
    for c in campaigns:
        if c["status"] != "ENABLED" or c["daily_budget"] <= 0:
            continue

        utilization = c["daily_spend_avg"] / c["daily_budget"]

        if utilization < BUDGET_UNDERSPEND_THRESHOLD:
            report.add(
                "WARNING", c["name"], "budget_pacing",
                f"Spending {utilization:.0%} of daily budget "
                f"(${c['daily_spend_avg']:.2f} / ${c['daily_budget']:.2f}). "
                f"Possible delivery issue or overly tight targeting.",
            )
        elif utilization > BUDGET_OVERSPEND_THRESHOLD:
            report.add(
                "WARNING", c["name"], "budget_pacing",
                f"Spending {utilization:.0%} of daily budget "
                f"(${c['daily_spend_avg']:.2f} / ${c['daily_budget']:.2f}). "
                f"Google may be front-loading spend.",
            )


def check_conversion_health(campaigns: list[dict],
                            report: AuditReport) -> None:
    """Flag campaigns with CPA anomalies or zero conversions despite spend."""
    # Calculate account-level average CPA (only from campaigns with conversions)
    total_cost = sum(c["cost"] for c in campaigns if c["conversions"] > 0)
    total_conv = sum(c["conversions"] for c in campaigns if c["conversions"] > 0)
    account_avg_cpa = total_cost / total_conv if total_conv > 0 else 0

    for c in campaigns:
        if c["status"] != "ENABLED":
            continue

        # Zero conversions with meaningful spend
        if c["conversions"] == 0 and c["cost"] > 100:
            report.add(
                "CRITICAL", c["name"], "conversion_volume",
                f"${c['cost']:.2f} spent with 0 conversions over the lookback period. "
                f"Check conversion tracking setup or campaign targeting.",
            )

        # CPA significantly above account average
        elif c["cpa"] > 0 and account_avg_cpa > 0:
            if c["cpa"] > account_avg_cpa * HIGH_CPA_MULTIPLIER:
                report.add(
                    "WARNING", c["name"], "high_cpa",
                    f"CPA ${c['cpa']:.2f} is {c['cpa'] / account_avg_cpa:.1f}x "
                    f"the account average (${account_avg_cpa:.2f}). "
                    f"Review targeting, bids, or landing pages.",
                )


def check_impression_share(campaigns: list[dict],
                           report: AuditReport) -> None:
    """Flag campaigns with low impression share or high budget-lost IS."""
    for c in campaigns:
        if c["status"] != "ENABLED" or c["channel"] != "SEARCH":
            continue

        if 0 < c["search_is"] < LOW_IMPRESSION_SHARE:
            report.add(
                "WARNING", c["name"], "low_impression_share",
                f"Search impression share is {c['search_is']:.0%}. "
                f"Significant opportunity being missed.",
            )

        if c["budget_lost_is"] > HIGH_BUDGET_LOST_IS:
            report.add(
                "CRITICAL", c["name"], "budget_capped",
                f"Losing {c['budget_lost_is']:.0%} of impressions due to budget. "
                f"Campaign is budget-constrained — increase budget or narrow targeting.",
            )


def check_naming_conventions(campaigns: list[dict],
                             report: AuditReport) -> None:
    """Flag campaigns that don't follow the standard naming convention."""
    for c in campaigns:
        if c["status"] == "REMOVED":
            continue

        if not NAMING_PATTERN.match(c["name"]):
            report.add(
                "INFO", c["name"], "naming_convention",
                f"Campaign name doesn't match pattern: "
                f"{{channel}}_{{geo}}_{{audience}}_{{objective}}. "
                f"Non-standard names make reporting and automation harder.",
            )


def check_auto_tagging(account_info: dict, report: AuditReport) -> None:
    """Verify auto-tagging is enabled for Analytics integration."""
    if not account_info.get("auto_tagging"):
        report.add(
            "WARNING", "(account-level)", "auto_tagging",
            "Auto-tagging is disabled. Google Analytics integration "
            "requires auto-tagging for accurate attribution.",
        )


def check_campaign_status_anomalies(campaigns: list[dict],
                                    report: AuditReport) -> None:
    """Flag paused campaigns that have recent spend (shouldn't happen)."""
    for c in campaigns:
        if c["status"] == "PAUSED" and c["cost"] > 0:
            report.add(
                "INFO", c["name"], "status_anomaly",
                f"Campaign is PAUSED but shows ${c['cost']:.2f} spend in the "
                f"lookback window. Likely paused mid-period.",
            )


# ── Report output ────────────────────────────────────────────────────────────

def print_report(report: AuditReport) -> None:
    """Print a formatted audit report to the console."""
    print("\n" + "=" * 72)
    print("  CAMPAIGN HEALTH AUDIT")
    print("=" * 72)
    print(f"  Account:    {report.account_name} ({report.account_id})")
    print(f"  Period:     Last {report.lookback_days} days")
    print(f"  Campaigns:  {report.campaigns_checked}")
    print(f"  Findings:   {len(report.findings)} "
          f"({report.critical_count} critical, {report.warning_count} warnings)")
    print("=" * 72)

    if not report.findings:
        print("\n  No issues found. Account looks healthy.\n")
        return

    # Group by severity
    for severity in ("CRITICAL", "WARNING", "INFO"):
        findings = [f for f in report.findings if f.severity == severity]
        if not findings:
            continue

        marker = {"CRITICAL": "!!!", "WARNING": " ! ", "INFO": " i "}[severity]
        print(f"\n  [{marker}] {severity} ({len(findings)})")
        print("  " + "-" * 68)

        for f in findings:
            print(f"  Campaign: {f.campaign}")
            print(f"  Check:    {f.check}")
            print(f"  Detail:   {f.detail}")
            print()


# ── Main ─────────────────────────────────────────────────────────────────────

def run_audit(config_path: str = DEFAULT_CONFIG_PATH,
              days: int = DEFAULT_LOOKBACK_DAYS) -> AuditReport:
    """Run the full campaign health audit."""
    client, customer_id = load_client(config_path)

    print(f"Pulling data for customer {customer_id} ({days}-day lookback)...")

    account_info = pull_account_info(client, customer_id)
    campaigns = pull_campaign_performance(client, customer_id, days)

    print(f"  Found {len(campaigns)} campaigns")

    report = AuditReport(
        account_name=account_info["name"],
        account_id=account_info["id"],
        lookback_days=days,
        campaigns_checked=len(campaigns),
    )

    # Run all checks
    check_auto_tagging(account_info, report)
    check_budget_pacing(campaigns, report, days)
    check_conversion_health(campaigns, report)
    check_impression_share(campaigns, report)
    check_naming_conventions(campaigns, report)
    check_campaign_status_anomalies(campaigns, report)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Ads campaign health audit"
    )
    parser.add_argument(
        "--config", type=str, default=DEFAULT_CONFIG_PATH,
        help=f"Path to google-ads.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"Lookback period in days (default: {DEFAULT_LOOKBACK_DAYS})",
    )
    args = parser.parse_args()

    report = run_audit(config_path=args.config, days=args.days)
    print_report(report)


if __name__ == "__main__":
    main()
