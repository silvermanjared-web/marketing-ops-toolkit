# Example Run

This example shows the intended shape of a marketing operations toolkit run using mock inputs. It is illustrative, not connected to live Gmail, Google Ads, or private account data.

The purpose of this file is to make the repo easier to inspect. It shows what an operator should expect from the active scripts without requiring access to private credentials or live accounts.

## Executable command map

| Workflow | Command | Writes to external system? |
|---|---|---|
| Inbox dry run | `python -m src.inbox.accelerator --dry` | No |
| Inbox status | `python -m src.inbox.accelerator --status` | No |
| Inbox reset | `python -m src.inbox.accelerator --reset` | No external write; resets local state |
| Inbox apply | `python -m src.inbox.accelerator` | Yes, after OAuth and rule review |
| Campaign health audit | `python -m src.audit.campaign_health --days 30` | No; reads Google Ads data |

## Inbox automation dry run

### Command

```bash
python -m src.inbox.accelerator --dry
```

### Sample console output

```text
Loaded 8 rules
Run #3 | phase=processing | rule=2/7 | labeled=284 | archived=196
[DRY RUN] Rule 2 (Platform alerts): would process 91 messages
[DRY RUN] Rule 3 (Vendor reporting): would process 142 messages
[DRY RUN] Rule 4 (Low-priority newsletters): would process 178 messages
Rule 5 (Recruiter and priority contacts): no matches, advancing.
Run #3 complete | 14s | labeled=284 | archived=196 | errors=0 | next_rule=6
```

### Operator readout

| Review area | Signal | Suggested action |
|---|---|---|
| Rule volume | Three rules would touch 411 messages | Confirm rules are scoped correctly before write run |
| Priority safety | Priority-contact rule had no matches | Confirm this is expected before archiving lower-priority mail |
| State behavior | Next run resumes from rule 6 | Use `--status` before applying changes |

## Inbox status check

### Command

```bash
python -m src.inbox.accelerator --status
```

### Sample console output

```text
=== Inbox Accelerator Status ===
Phase:      processing
Rule index: 6
Labeled:    284
Archived:   196
Errors:     0
Runs:       3
Last run:   2026-06-19T13:42:05+00:00
```

## Campaign health audit

### Command

```bash
python -m src.audit.campaign_health --days 30
```

### Sample console output

```text
Pulling data for customer 1234567890 (30-day lookback)...
  Found 36 campaigns

========================================================================
  CAMPAIGN HEALTH AUDIT
========================================================================
  Account:    Demo Growth Account (1234567890)
  Period:     Last 30 days
  Campaigns:  36
  Findings:   6 (2 critical, 3 warnings)
========================================================================

  [!!!] CRITICAL (2)
  --------------------------------------------------------------------
  Campaign: search_us_prospecting_leads
  Check:    conversion_volume
  Detail:   $1,248.32 spent with 0 conversions over the lookback period. Check conversion tracking setup or campaign targeting.

  Campaign: search_us_brand_leads
  Check:    budget_capped
  Detail:   Losing 24% of impressions due to budget. Campaign is budget-constrained — increase budget or narrow targeting.

  [ ! ] WARNING (3)
  --------------------------------------------------------------------
  Campaign: pmax_us_prospecting_enrollments
  Check:    budget_pacing
  Detail:   Spending 118% of daily budget ($354.00 / $300.00). Google may be front-loading spend.

  Campaign: search_us_remarketing_leads
  Check:    high_cpa
  Detail:   CPA $182.41 is 2.4x the account average ($75.33). Review targeting, bids, or landing pages.

  Campaign: (account-level)
  Check:    auto_tagging
  Detail:   Auto-tagging is disabled. Google Analytics integration requires auto-tagging for accurate attribution.
```

### Operator readout

| Severity | What it means | Next action |
|---|---|---|
| Critical | Spend or delivery signal may distort performance reads | Review before budget or forecast decisions |
| Warning | Campaign may need correction or closer inspection | Queue for next optimization pass |
| Info | Hygiene issue affecting automation or reporting clarity | Fix when operationally convenient |

## What this demonstrates

The toolkit is designed to make recurring marketing operations work easier to inspect and safer to execute. Dry-run behavior, state awareness, structured summaries, and explicit findings help operators review before making changes.

## Notes

- This example uses mock data.
- Do not commit live exports, private campaign data, account IDs, credentials, or tokens.
- Dry-run mode should be used before applying inbox changes.
- Google Ads audit output should be treated as a diagnostic prompt for human review, not as an automated budget decision.
