"""
Executive Performance Brief Generator.

Pulls key metrics from Google Ads, calculates period-over-period changes,
flags statistical anomalies, and generates a formatted console report.

Designed for weekly or monthly executive updates — a single command that
produces a summary a CMO can read in 60 seconds.

Usage:
    python -m src.reporting.exec_brief
    python -m src.reporting.exec_brief --config config/google-ads.yaml
    python -m src.reporting.exec_brief --period 14  # 14-day comparison
    python -m src.reporting.exec_brief --format markdown
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = "config/google-ads.yaml"
DEFAULT_PERIOD_DAYS = 7

# Anomaly detection: flag metrics that deviate more than N standard
# deviations from the trailing average.
ANOMALY_THRESHOLD_STDEV = 2.0
# Minimum data points needed for anomaly detection
MIN_PERIODS_FOR_ANOMALY = 4

# Change thresholds for directional indicators
SIGNIFICANT_CHANGE_PCT = 10.0


@dataclass
class MetricSummary:
    """A single metric with current vs. prior period comparison."""
    name: str
    current: float
    prior: float
    format_str: str = "{:.2f}"

    @property
    def change(self) -> float:
        if self.prior == 0:
            return 0.0
        return (self.current - self.prior) / self.prior * 100

    @property
    def direction(self) -> str:
        if abs(self.change) < SIGNIFICANT_CHANGE_PCT:
            return "flat"
        return "up" if self.change > 0 else "down"

    def formatted_current(self) -> str:
        return self.format_str.format(self.current)

    def formatted_prior(self) -> str:
        return self.format_str.format(self.prior)


@dataclass
class Anomaly:
    """A metric that deviates significantly from its trailing average."""
    campaign: str
    metric: str
    value: float
    mean: float
    stdev: float
    deviations: float


@dataclass
class ExecBrief:
    """Complete executive briefing data."""
    account_name: str
    account_id: str
    period_days: int
    current_start: str
    current_end: str
    prior_start: str
    prior_end: str
    metrics: list[MetricSummary] = field(default_factory=list)
    campaign_table: list[dict] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)


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


def pull_period_metrics(client: GoogleAdsClient, customer_id: str,
                        start_date: str, end_date: str) -> dict:
    """Pull aggregate account-level metrics for a date range."""
    query = f"""
        SELECT metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.conversions_value,
               metrics.ctr, metrics.average_cpc, metrics.cost_per_conversion
        FROM customer
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    rows = run_query(client, customer_id, query)

    totals = {
        "cost": 0.0, "impressions": 0, "clicks": 0,
        "conversions": 0.0, "conv_value": 0.0,
    }
    for r in rows:
        totals["cost"] += r.metrics.cost_micros / 1_000_000
        totals["impressions"] += r.metrics.impressions
        totals["clicks"] += r.metrics.clicks
        totals["conversions"] += r.metrics.conversions
        totals["conv_value"] += r.metrics.conversions_value

    # Derived metrics
    totals["ctr"] = (
        totals["clicks"] / totals["impressions"] * 100
        if totals["impressions"] > 0 else 0
    )
    totals["avg_cpc"] = (
        totals["cost"] / totals["clicks"]
        if totals["clicks"] > 0 else 0
    )
    totals["cpa"] = (
        totals["cost"] / totals["conversions"]
        if totals["conversions"] > 0 else 0
    )
    totals["roas"] = (
        totals["conv_value"] / totals["cost"]
        if totals["cost"] > 0 else 0
    )

    return totals


def pull_campaign_breakdown(client: GoogleAdsClient, customer_id: str,
                            start_date: str, end_date: str) -> list[dict]:
    """Pull campaign-level metrics for the current period."""
    query = f"""
        SELECT campaign.name, campaign.status,
               campaign.advertising_channel_type,
               metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND campaign.status != 'REMOVED'
          AND metrics.cost_micros > 0
        ORDER BY metrics.cost_micros DESC
    """
    rows = run_query(client, customer_id, query)
    campaigns = []
    for r in rows:
        cost = r.metrics.cost_micros / 1_000_000
        campaigns.append({
            "name": r.campaign.name,
            "channel": r.campaign.advertising_channel_type.name,
            "cost": cost,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "conversions": r.metrics.conversions,
            "cpa": (
                r.metrics.cost_per_conversion / 1_000_000
                if r.metrics.cost_per_conversion else 0
            ),
        })
    return campaigns


def pull_daily_metrics(client: GoogleAdsClient, customer_id: str,
                       days: int) -> list[dict]:
    """Pull daily account-level metrics for anomaly detection.

    Pulls a longer trailing window (4x the period) to build a baseline.
    """
    trailing_days = days * (MIN_PERIODS_FOR_ANOMALY + 2)
    start = (datetime.now() - timedelta(days=trailing_days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT segments.date,
               metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions
        FROM customer
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY segments.date ASC
    """
    rows = run_query(client, customer_id, query)
    daily = []
    for r in rows:
        daily.append({
            "date": str(r.segments.date),
            "cost": r.metrics.cost_micros / 1_000_000,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "conversions": r.metrics.conversions,
        })
    return daily


# ── Anomaly detection ────────────────────────────────────────────────────────

def detect_anomalies(daily_metrics: list[dict],
                     period_days: int) -> list[Anomaly]:
    """Detect statistical anomalies by comparing the most recent period
    against the trailing baseline.

    Uses simple z-score detection: if a metric in the current period
    deviates more than ANOMALY_THRESHOLD_STDEV from the trailing mean,
    it's flagged.
    """
    if len(daily_metrics) < period_days * MIN_PERIODS_FOR_ANOMALY:
        return []

    # Split into current period and trailing baseline
    current = daily_metrics[-period_days:]
    baseline = daily_metrics[:-period_days]

    # Aggregate into period-sized buckets for the baseline
    baseline_periods: list[dict[str, float]] = []
    for i in range(0, len(baseline), period_days):
        chunk = baseline[i:i + period_days]
        if len(chunk) < period_days:
            continue
        baseline_periods.append({
            "cost": sum(d["cost"] for d in chunk),
            "clicks": sum(d["clicks"] for d in chunk),
            "conversions": sum(d["conversions"] for d in chunk),
            "impressions": sum(d["impressions"] for d in chunk),
        })

    if len(baseline_periods) < MIN_PERIODS_FOR_ANOMALY:
        return []

    current_agg = {
        "cost": sum(d["cost"] for d in current),
        "clicks": sum(d["clicks"] for d in current),
        "conversions": sum(d["conversions"] for d in current),
        "impressions": sum(d["impressions"] for d in current),
    }

    anomalies: list[Anomaly] = []

    for metric in ("cost", "clicks", "conversions", "impressions"):
        values = [p[metric] for p in baseline_periods]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        stdev = math.sqrt(variance) if variance > 0 else 0

        if stdev == 0:
            continue

        current_val = current_agg[metric]
        z_score = abs(current_val - mean) / stdev

        if z_score >= ANOMALY_THRESHOLD_STDEV:
            anomalies.append(Anomaly(
                campaign="(account-level)",
                metric=metric,
                value=current_val,
                mean=mean,
                stdev=stdev,
                deviations=z_score,
            ))

    return anomalies


# ── Brief construction ───────────────────────────────────────────────────────

def build_brief(client: GoogleAdsClient, customer_id: str,
                period_days: int) -> ExecBrief:
    """Build the complete executive brief."""
    now = datetime.now()
    current_end = now.strftime("%Y-%m-%d")
    current_start = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
    prior_end = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
    prior_start = (now - timedelta(days=period_days * 2)).strftime("%Y-%m-%d")

    print(f"Pulling data for customer {customer_id}...")
    print(f"  Current period: {current_start} to {current_end}")
    print(f"  Prior period:   {prior_start} to {prior_end}")

    account_info = pull_account_info(client, customer_id)
    current = pull_period_metrics(client, customer_id, current_start, current_end)
    prior = pull_period_metrics(client, customer_id, prior_start, prior_end)
    campaigns = pull_campaign_breakdown(client, customer_id,
                                        current_start, current_end)
    daily = pull_daily_metrics(client, customer_id, period_days)

    # Build metric comparisons
    metrics = [
        MetricSummary("Spend", current["cost"], prior["cost"], "${:,.2f}"),
        MetricSummary("Impressions", current["impressions"],
                      prior["impressions"], "{:,.0f}"),
        MetricSummary("Clicks", current["clicks"], prior["clicks"], "{:,.0f}"),
        MetricSummary("CTR", current["ctr"], prior["ctr"], "{:.2f}%"),
        MetricSummary("Avg CPC", current["avg_cpc"], prior["avg_cpc"], "${:.2f}"),
        MetricSummary("Conversions", current["conversions"],
                      prior["conversions"], "{:,.1f}"),
        MetricSummary("CPA", current["cpa"], prior["cpa"], "${:.2f}"),
        MetricSummary("ROAS", current["roas"], prior["roas"], "{:.2f}x"),
    ]

    anomalies = detect_anomalies(daily, period_days)

    return ExecBrief(
        account_name=account_info["name"],
        account_id=account_info["id"],
        period_days=period_days,
        current_start=current_start,
        current_end=current_end,
        prior_start=prior_start,
        prior_end=prior_end,
        metrics=metrics,
        campaign_table=campaigns,
        anomalies=anomalies,
    )


# ── Output formatters ────────────────────────────────────────────────────────

def direction_indicator(m: MetricSummary) -> str:
    """Return a text indicator for metric direction."""
    if m.direction == "up":
        return f"+{m.change:.1f}%"
    elif m.direction == "down":
        return f"{m.change:.1f}%"
    return "flat"


def print_console(brief: ExecBrief) -> None:
    """Print the executive brief to the console."""
    print("\n" + "=" * 72)
    print("  EXECUTIVE PERFORMANCE BRIEF")
    print("=" * 72)
    print(f"  Account:  {brief.account_name} ({brief.account_id})")
    print(f"  Period:   {brief.current_start} to {brief.current_end} "
          f"({brief.period_days} days)")
    print(f"  Compared: {brief.prior_start} to {brief.prior_end}")
    print("=" * 72)

    # Key metrics
    print("\n  KEY METRICS")
    print("  " + "-" * 68)
    print(f"  {'Metric':<16} {'Current':>12} {'Prior':>12} {'Change':>10}")
    print("  " + "-" * 68)

    for m in brief.metrics:
        indicator = direction_indicator(m)
        print(f"  {m.name:<16} {m.formatted_current():>12} "
              f"{m.formatted_prior():>12} {indicator:>10}")

    # Campaign breakdown
    if brief.campaign_table:
        print(f"\n  CAMPAIGN BREAKDOWN (top {min(len(brief.campaign_table), 10)})")
        print("  " + "-" * 68)
        print(f"  {'Campaign':<30} {'Spend':>10} {'Conv':>6} {'CPA':>10}")
        print("  " + "-" * 68)

        for c in brief.campaign_table[:10]:
            name = c["name"][:28] + ".." if len(c["name"]) > 30 else c["name"]
            cpa_str = f"${c['cpa']:.2f}" if c["cpa"] > 0 else "n/a"
            print(f"  {name:<30} ${c['cost']:>9,.2f} {c['conversions']:>6.1f} "
                  f"{cpa_str:>10}")

    # Anomalies
    if brief.anomalies:
        print(f"\n  ANOMALIES DETECTED ({len(brief.anomalies)})")
        print("  " + "-" * 68)
        for a in brief.anomalies:
            direction = "above" if a.value > a.mean else "below"
            print(f"  {a.metric.upper()}: {a.value:,.1f} is {a.deviations:.1f} "
                  f"std devs {direction} trailing avg ({a.mean:,.1f})")
    else:
        print("\n  No anomalies detected.")

    print("\n" + "=" * 72 + "\n")


def print_markdown(brief: ExecBrief) -> None:
    """Print the executive brief in Markdown format."""
    print(f"# Executive Performance Brief")
    print(f"\n**Account:** {brief.account_name} ({brief.account_id})  ")
    print(f"**Period:** {brief.current_start} to {brief.current_end} "
          f"({brief.period_days} days)  ")
    print(f"**Compared to:** {brief.prior_start} to {brief.prior_end}\n")

    # Key metrics table
    print("## Key Metrics\n")
    print(f"| Metric | Current | Prior | Change |")
    print(f"|--------|---------|-------|--------|")
    for m in brief.metrics:
        indicator = direction_indicator(m)
        print(f"| {m.name} | {m.formatted_current()} | "
              f"{m.formatted_prior()} | {indicator} |")

    # Campaign breakdown
    if brief.campaign_table:
        print(f"\n## Campaign Breakdown\n")
        print(f"| Campaign | Spend | Conv | CPA |")
        print(f"|----------|-------|------|-----|")
        for c in brief.campaign_table[:10]:
            cpa_str = f"${c['cpa']:.2f}" if c["cpa"] > 0 else "n/a"
            print(f"| {c['name']} | ${c['cost']:,.2f} | "
                  f"{c['conversions']:.1f} | {cpa_str} |")

    # Anomalies
    if brief.anomalies:
        print(f"\n## Anomalies\n")
        for a in brief.anomalies:
            direction = "above" if a.value > a.mean else "below"
            print(f"- **{a.metric.upper()}**: {a.value:,.1f} is "
                  f"{a.deviations:.1f} std devs {direction} "
                  f"trailing avg ({a.mean:,.1f})")

    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate executive performance brief from Google Ads data"
    )
    parser.add_argument(
        "--config", type=str, default=DEFAULT_CONFIG_PATH,
        help=f"Path to google-ads.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--period", type=int, default=DEFAULT_PERIOD_DAYS,
        help=f"Comparison period in days (default: {DEFAULT_PERIOD_DAYS})",
    )
    parser.add_argument(
        "--format", type=str, choices=["console", "markdown"],
        default="console",
        help="Output format (default: console)",
    )
    args = parser.parse_args()

    client, customer_id = load_client(args.config)
    brief = build_brief(client, customer_id, args.period)

    if args.format == "markdown":
        print_markdown(brief)
    else:
        print_console(brief)


if __name__ == "__main__":
    main()
