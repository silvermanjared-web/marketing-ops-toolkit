# Marketing Ops Toolkit

Practical automation scripts for performance marketing operations — inbox management, platform auditing, and reporting workflows.

## Problem

Marketing operations teams lose time and budget to predictable failures: campaigns pacing incorrectly, conversion tracking going stale, spend leaking into irrelevant search terms, and reports assembled manually every week. These scripts automate the detection and diagnosis so operators can focus on decisions.

## Components

### Inbox Automation (`src/inbox/`)
Rule-based email processing using the Gmail API. Categorizes, labels, archives, and prioritizes messages in batch — processing thousands of emails in single API calls.

- **Rule engine** with configurable pattern matching (sender, subject, keywords)
- **Batch processing** — labels and archives up to 1,000 messages per API call  
- **State persistence** — tracks progress across runs, resumes where it left off
- **Dry-run mode** — preview changes before applying

### Platform Audit (`src/audit/`)
Automated health checks for Google Ads accounts.

- **Campaign structure audit** — hierarchy validation, naming convention checks
- **Budget pacing** — spend vs. target tracking with alert thresholds
- **Conversion tracking audit** — validates tracking setup, identifies gaps
- **Search term analysis** — waste identification and negative keyword recommendations

### Reporting (`src/reporting/`)
Executive briefing generation from platform data.

- **Performance summary** — key metrics with period-over-period comparison
- **Anomaly flagging** — statistical deviation detection across campaigns
- **Formatted output** — generates clean reports (PDF, Markdown, or console)

## Stack

- Python 3.12+
- Google Ads API (`google-ads`)
- Gmail API (`google-api-python-client`)
- No frameworks, no ORMs, no unnecessary abstraction

## Usage

```bash
# Gmail inbox automation
python -m src.inbox.accelerator --dry        # Preview what would change
python -m src.inbox.accelerator              # Process inbox

# Google Ads audit
python -m src.audit.campaign_health          # Campaign structure check
python -m src.audit.conversion_tracking      # Tracking validation
python -m src.audit.search_terms             # Waste analysis

# Reporting
python -m src.reporting.exec_brief           # Generate executive summary
```

## Configuration

```bash
cp config/gmail_rules.example.json config/gmail_rules.json
cp config/ads_accounts.example.json config/ads_accounts.json
cp config/google-ads.example.yaml config/google-ads.yaml
```

See [config/README.md](config/README.md) for setup instructions.

## Design Philosophy

- **Single-purpose scripts** — each file does one thing well
- **Batch over loop** — minimize API calls, maximize throughput
- **Dry-run everything** — preview before modifying
- **State machines** — resume-safe, idempotent operations
- **No magic** — explicit configuration, readable code
