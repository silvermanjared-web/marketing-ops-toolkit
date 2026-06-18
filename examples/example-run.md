# Example Run

This example shows the intended shape of a marketing operations toolkit run using mock inputs. It is illustrative, not connected to live Gmail, Google Ads, or private account data.

## Inbox automation dry run

### Command

```bash
python -m src.inbox.accelerator --dry
```

### Sample output

```text
Inbox Automation
Mode: dry-run
Messages scanned: 1,250
Rules matched: 438
Labels proposed: 392
Archive candidates: 311
Manual review candidates: 27
Status: preview complete
```

### Sample summary

| Action | Count | Notes |
|---|---:|---|
| Apply label: Vendor / Reporting | 142 | Recurring reporting emails |
| Apply label: Platform Alerts | 91 | Google Ads and analytics notices |
| Archive low-priority newsletters | 178 | Non-actionable messages |
| Keep in inbox for review | 27 | Possible action items |

## Platform audit sample

### Command

```bash
python -m src.audit.campaign_health
```

### Sample output

```text
Campaign Health Audit
Accounts checked: 2
Campaigns checked: 36
Naming issues: 4
Budget pacing alerts: 3
Conversion tracking warnings: 2
Status: review recommended
```

### Sample findings

| Severity | Finding | Suggested action |
|---|---|---|
| High | Campaign pacing above threshold | Review budget allocation before next reporting cycle |
| Medium | Naming convention mismatch | Correct campaign naming before dashboard refresh |
| Medium | Conversion action not recently active | Confirm tracking status before drawing conclusions |

## What this demonstrates

The toolkit is designed to make recurring marketing operations work easier to inspect and safer to execute. Dry-run behavior, structured summaries, and explicit findings help operators review before making changes.

## Notes

- This example uses mock data.
- Do not commit live exports, private campaign data, account IDs, credentials, or tokens.
- Dry-run mode should be used before applying inbox or platform changes.
