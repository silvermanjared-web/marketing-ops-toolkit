# Configuration

## Gmail API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Enable the **Gmail API**
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON and save as `credentials.json` in the project root
6. On first run, a browser window will open for authorization — the resulting token is saved as `token.json`

Reference: [Gmail API Python Quickstart](https://developers.google.com/gmail/api/quickstart/python)

### Gmail Rules

```bash
cp config/gmail_rules.example.json config/gmail_rules.json
```

Edit `gmail_rules.json` to add your own sender patterns, subject filters, and label mappings. Each rule needs:

- `name` — human-readable description
- `query` — Gmail search query (same syntax as the Gmail search bar)
- `label` — target label (created automatically if it doesn't exist)
- `archive` — whether to remove from inbox
- `mark_read` — whether to mark as read

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

### Accounts Config

```bash
cp config/ads_accounts.example.json config/ads_accounts.json
```

Optional multi-account config for running audits across several accounts. Also holds brand terms and competitor lists for search term classification.
