"""
Google Ads Search Term Waste Analysis.

Pulls the search term report, classifies terms into themes, calculates
waste by category, and recommends negative keywords.

Categories:
- Brand: queries containing your brand name
- Competitor: queries containing known competitor names
- Jobs: job-seeking queries (irrelevant for most advertisers)
- Informational: research queries unlikely to convert
- Irrelevant: off-topic queries with no commercial intent
- On-target: queries matching intended targeting

Usage:
    python -m src.audit.search_terms
    python -m src.audit.search_terms --config config/google-ads.yaml --days 60
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from google.ads.googleads.client import GoogleAdsClient


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_CONFIG_PATH = "config/google-ads.yaml"
DEFAULT_LOOKBACK_DAYS = 30

# Classification patterns — customize these for your business
# These are generic examples; real implementations should load from config.

JOB_PATTERNS = re.compile(
    r"\b(job|jobs|career|careers|hiring|salary|glassdoor|indeed|"
    r"work from home|remote work|interview|resume)\b",
    re.IGNORECASE,
)

INFORMATIONAL_PATTERNS = re.compile(
    r"\b(what is|how to|definition|meaning|wiki|wikipedia|"
    r"tutorial|guide|course|certification|reddit|quora)\b",
    re.IGNORECASE,
)

# Competitor names — replace with actual competitors in your config
DEFAULT_COMPETITORS = [
    "competitor-a",
    "competitor-b",
    "competitor-c",
]

# Brand terms — replace with your actual brand terms
DEFAULT_BRAND_TERMS = [
    "acme",
    "acme corp",
]

# Minimum spend to flag a term as wasteful
WASTE_THRESHOLD_SPEND = 5.00
# Minimum spend with zero conversions to flag
ZERO_CONV_THRESHOLD = 25.00


@dataclass
class ClassifiedTerm:
    """A search term with its classification and metrics."""
    term: str
    category: str
    campaign: str
    ad_group: str
    cost: float
    impressions: int
    clicks: int
    conversions: float
    ctr: float


@dataclass
class WasteReport:
    """Search term waste analysis results."""
    account_name: str
    account_id: str
    lookback_days: int
    total_terms: int
    total_spend: float
    categories: dict[str, list[ClassifiedTerm]] = field(default_factory=dict)
    negative_recommendations: list[str] = field(default_factory=list)

    @property
    def waste_spend(self) -> float:
        """Total spend on wasteful categories."""
        waste_cats = {"jobs", "competitor", "informational", "irrelevant"}
        return sum(
            t.cost
            for cat, terms in self.categories.items()
            if cat in waste_cats
            for t in terms
        )


# ── Google Ads client ────────────────────────────────────────────────────────

def load_client(config_path: str) -> tuple[GoogleAdsClient, str, dict]:
    """Load Google Ads client, customer ID, and classification config."""
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

    # Optional classification overrides in config
    classification = {
        "brand_terms": config.get("brand_terms", DEFAULT_BRAND_TERMS),
        "competitors": config.get("competitors", DEFAULT_COMPETITORS),
    }

    return client, str(customer_id).replace("-", ""), classification


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


def pull_search_terms(client: GoogleAdsClient, customer_id: str,
                      days: int) -> list[dict]:
    """Pull the search term report for the lookback period."""
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT search_term_view.search_term,
               search_term_view.status,
               campaign.name, ad_group.name,
               metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.ctr
        FROM search_term_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY metrics.cost_micros DESC
        LIMIT 1000
    """
    rows = run_query(client, customer_id, query)
    terms = []
    for r in rows:
        terms.append({
            "term": r.search_term_view.search_term,
            "status": r.search_term_view.status.name,
            "campaign": r.campaign.name,
            "ad_group": r.ad_group.name,
            "cost": r.metrics.cost_micros / 1_000_000,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "conversions": r.metrics.conversions,
            "ctr": r.metrics.ctr,
        })
    return terms


# ── Classification ───────────────────────────────────────────────────────────

def classify_term(term: str, brand_terms: list[str],
                  competitors: list[str]) -> str:
    """Classify a search term into a category.

    Priority order:
        1. Brand (contains brand name)
        2. Competitor (contains competitor name)
        3. Jobs (job-seeking intent)
        4. Informational (research/educational intent)
        5. On-target (everything else)
    """
    term_lower = term.lower()

    # Brand
    for brand in brand_terms:
        if brand.lower() in term_lower:
            return "brand"

    # Competitor
    for comp in competitors:
        if comp.lower() in term_lower:
            return "competitor"

    # Jobs
    if JOB_PATTERNS.search(term):
        return "jobs"

    # Informational
    if INFORMATIONAL_PATTERNS.search(term):
        return "informational"

    return "on_target"


def classify_all_terms(raw_terms: list[dict],
                       brand_terms: list[str],
                       competitors: list[str]) -> dict[str, list[ClassifiedTerm]]:
    """Classify all search terms and group by category."""
    categories: dict[str, list[ClassifiedTerm]] = defaultdict(list)

    for t in raw_terms:
        category = classify_term(t["term"], brand_terms, competitors)
        classified = ClassifiedTerm(
            term=t["term"],
            category=category,
            campaign=t["campaign"],
            ad_group=t["ad_group"],
            cost=t["cost"],
            impressions=t["impressions"],
            clicks=t["clicks"],
            conversions=t["conversions"],
            ctr=t["ctr"],
        )
        categories[category].append(classified)

    return dict(categories)


# ── Negative keyword recommendations ────────────────────────────────────────

def recommend_negatives(categories: dict[str, list[ClassifiedTerm]]) -> list[str]:
    """Generate negative keyword recommendations from wasteful terms.

    Recommends negatives for:
    - Job-related terms with any spend
    - Competitor terms with high spend and no conversions
    - Informational terms above the waste threshold
    - Any term with significant spend and zero conversions
    """
    recommendations: list[str] = []
    seen: set[str] = set()

    # All job terms
    for t in categories.get("jobs", []):
        if t.cost >= WASTE_THRESHOLD_SPEND and t.term not in seen:
            recommendations.append(f"[EXACT] {t.term}  (jobs, ${t.cost:.2f} waste)")
            seen.add(t.term)

    # Competitor terms with no conversions
    for t in categories.get("competitor", []):
        if t.conversions == 0 and t.cost >= WASTE_THRESHOLD_SPEND and t.term not in seen:
            recommendations.append(
                f"[EXACT] {t.term}  (competitor, ${t.cost:.2f}, 0 conv)"
            )
            seen.add(t.term)

    # Informational terms
    for t in categories.get("informational", []):
        if t.cost >= WASTE_THRESHOLD_SPEND and t.term not in seen:
            recommendations.append(
                f"[PHRASE] {t.term}  (informational, ${t.cost:.2f})"
            )
            seen.add(t.term)

    # High-spend zero-conversion on-target terms (potential waste)
    for t in categories.get("on_target", []):
        if t.conversions == 0 and t.cost >= ZERO_CONV_THRESHOLD and t.term not in seen:
            recommendations.append(
                f"[REVIEW] {t.term}  (${t.cost:.2f}, 0 conv — review before adding)"
            )
            seen.add(t.term)

    return sorted(recommendations, key=lambda x: x.split("$")[1] if "$" in x else "0",
                  reverse=True)


# ── Report output ────────────────────────────────────────────────────────────

def print_report(report: WasteReport) -> None:
    """Print formatted search term waste analysis."""
    print("\n" + "=" * 72)
    print("  SEARCH TERM WASTE ANALYSIS")
    print("=" * 72)
    print(f"  Account:       {report.account_name} ({report.account_id})")
    print(f"  Period:        Last {report.lookback_days} days")
    print(f"  Terms pulled:  {report.total_terms}")
    print(f"  Total spend:   ${report.total_spend:,.2f}")
    print(f"  Waste spend:   ${report.waste_spend:,.2f} "
          f"({report.waste_spend / report.total_spend:.1%} of total)"
          if report.total_spend > 0 else "")
    print("=" * 72)

    # Category breakdown
    print("\n  CATEGORY BREAKDOWN")
    print("  " + "-" * 68)
    print(f"  {'Category':<16} {'Terms':>6} {'Spend':>12} {'Clicks':>8} {'Conv':>8}")
    print("  " + "-" * 68)

    for cat in ("brand", "on_target", "competitor", "jobs", "informational"):
        terms = report.categories.get(cat, [])
        if not terms:
            continue
        cat_spend = sum(t.cost for t in terms)
        cat_clicks = sum(t.clicks for t in terms)
        cat_conv = sum(t.conversions for t in terms)
        print(f"  {cat:<16} {len(terms):>6} ${cat_spend:>10,.2f} {cat_clicks:>8} {cat_conv:>8.1f}")

    # Top waste terms
    waste_cats = {"jobs", "competitor", "informational"}
    waste_terms = [
        t for cat, terms in report.categories.items()
        if cat in waste_cats
        for t in terms
    ]
    waste_terms.sort(key=lambda t: t.cost, reverse=True)

    if waste_terms:
        print(f"\n  TOP WASTE TERMS (showing up to 15)")
        print("  " + "-" * 68)
        for t in waste_terms[:15]:
            print(f"  ${t.cost:>8.2f}  {t.clicks:>4} clicks  "
                  f"{t.conversions:>4.1f} conv  [{t.category}] {t.term}")

    # Negative recommendations
    if report.negative_recommendations:
        print(f"\n  NEGATIVE KEYWORD RECOMMENDATIONS ({len(report.negative_recommendations)})")
        print("  " + "-" * 68)
        for rec in report.negative_recommendations[:20]:
            print(f"  {rec}")

    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def run_audit(config_path: str = DEFAULT_CONFIG_PATH,
              days: int = DEFAULT_LOOKBACK_DAYS) -> WasteReport:
    """Run the full search term waste analysis."""
    client, customer_id, classification = load_client(config_path)

    print(f"Pulling search terms for customer {customer_id} "
          f"({days}-day lookback)...")

    account_info = pull_account_info(client, customer_id)
    raw_terms = pull_search_terms(client, customer_id, days)

    print(f"  Found {len(raw_terms)} search terms")

    categories = classify_all_terms(
        raw_terms,
        brand_terms=classification["brand_terms"],
        competitors=classification["competitors"],
    )

    negatives = recommend_negatives(categories)

    total_spend = sum(t["cost"] for t in raw_terms)

    report = WasteReport(
        account_name=account_info["name"],
        account_id=account_info["id"],
        lookback_days=days,
        total_terms=len(raw_terms),
        total_spend=total_spend,
        categories=categories,
        negative_recommendations=negatives,
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Ads search term waste analysis"
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
