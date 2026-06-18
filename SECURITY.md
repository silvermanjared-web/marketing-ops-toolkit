# Security Policy

## Supported Versions

This repository contains practical marketing operations automation scripts for inbox processing, platform auditing, and reporting workflows. It may interact with Gmail, Google Ads, local configuration files, and generated reports depending on local setup.

Security updates apply to the current `main` branch only.

| Version / Branch | Supported |
|---|---|
| `main` | :white_check_mark: |
| Archived branches, forks, or local copies | :x: |

## Scope

Security-sensitive issues may include:

- Accidentally committed secrets, API keys, OAuth tokens, credentials, or private URLs
- Unsafe handling of Gmail or Google Ads configuration files
- Example configuration files that could encourage exposing credentials
- Scripts that modify inbox state, labels, archived messages, or reporting files without adequate preview
- Logs, reports, exports, or generated files that may contain sensitive account, campaign, or customer information
- Platform-audit logic that exposes account identifiers or private performance data

Out of scope:

- General feature requests
- Campaign strategy recommendations
- Non-security bugs in local scripts
- Low-signal automated reports that do not apply to this repository
- Misconfiguration in a user's local environment outside the documented setup
- Issues requiring access to private systems not included in the repo

## Reporting a Vulnerability

Please do not open a public GitHub issue for security-sensitive concerns.

To report a vulnerability or sensitive-content exposure, contact:

**Jared Silverman**  
**Email:** silverman.jared@gmail.com

Please include:

- A short description of the concern
- The affected file, script, command, or configuration if known
- Why the issue may create security, privacy, or data-exposure risk
- Any suggested remediation
- Whether the information appears to be publicly accessible

## Response Expectations

Good-faith reports will be reviewed as soon as practical.

If the report is accepted, remediation may include:

- Removing or redacting sensitive content
- Rotating exposed credentials or tokens
- Updating examples, documentation, or defaults
- Adding clearer dry-run, confirmation, or local-safety guidance
- Revising logging, export, or state-management behavior

If the report is declined, the reason will be explained when appropriate.

## Disclosure Policy

Please allow time for review and remediation before sharing any security-sensitive concern publicly.

This repository is intended to support responsible marketing operations automation. Reports that help keep the project safe, accurate, and appropriately scoped are welcome.
