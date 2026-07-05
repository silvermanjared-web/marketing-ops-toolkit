# Configuration

## Gmail API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Enable the **Gmail API**
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON and save it as an ignored local file named `credentials.json`
6. On first authorization, the resulting token is saved as an ignored local file named `token.json`

Reference: [Gmail API Python Quickstart](https://developers.google.com/gmail/api/quickstart/python)

Do not commit OAuth credentials or tokens. The repository `.gitignore` excludes the default local filenames, but you should still treat them as private machine-local files.

### Gmail Rules

```bash
cp config/gmail_rules.example.json config/gmail_rules.json
```

Edit `gmail_rules.json` to add your own sender patterns, subject filters, and label mappings. Each rule needs:

- `name` — human-readable description
- `query` — Gmail search query (same syntax as the Gmail search bar)
- `label` — target label (created automatically if it doesn't exist)
- `archive` — whether to remove from inbox
- `mark_read` — whether to mark as read; keep this `false` unless the rule is narrow and intentionally low-risk

Run the inbox accelerator without flags first. It defaults to a dry run and does not modify Gmail or local processing state. Use `--apply` only after reviewing the matched rules.

## Google Ads API Setup

1. Apply for a [Google Ads API developer token](https://developers.google.com/google-ads/api/docs/get-started/dev-token)
2. Create OAuth 2.0 credentials in the [Google Cloud Console](https://console.cloud.google.com/)
3. Generate a refresh token using the [OAuth2 playground](https://developers.google.com/oauthplayground/) or the Google Ads API client library auth helper

```bash
cp config/google-ads.example.yaml config/google-ads.yaml
```

Fill in your credentials:

- `developer_token` — from Google Ads API Center
- `client_id` / `client_secret` — from Google Cloud Console OAuth credentials
- `refresh_token` — generated via OAuth flow
- `login_customer_id` — your MCC ID (without dashes) if using a manager account
- `customer_id` — the specific account to audit

Reference: [Google Ads API Authentication](https://developers.google.com/google-ads/api/docs/oauth/overview)

Do not commit `config/google-ads.yaml` or any copied output from live accounts. Public examples should use synthetic account names, IDs, and performance data only.

### Accounts Config

```bash
cp config/ads_accounts.example.json config/ads_accounts.json
```

Optional multi-account config for running audits across several accounts. Also holds brand terms and competitor lists for search term classification.
