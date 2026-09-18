# Security Policy

## Supported Versions


The following table shows which versions of Health Insights Agent are currently supported with security updates. Only the latest major release is actively maintained; older versions may not receive security patches.

| Version    | Supported          |
|------------|-------------------|
| main (latest) | :white_check_mark: |
| previous releases | :x:                |


## Reporting a Vulnerability

To report a security vulnerability:

1. Contact the current project maintainer through the private reporting channel configured for this repository.
2. Provide as much detail as possible, including steps to reproduce and potential impact.
3. You can expect an initial response within 72 hours. If the vulnerability is confirmed, we will work to release a fix as soon as possible and notify you when it is available.
4. If the vulnerability is declined, you will receive an explanation.

## Handling sensitive data

Do not include health reports, chat messages, passwords, API keys, access tokens, refresh tokens, or user contact details in issue reports. Use a minimal, fictional reproduction whenever possible. If the report requires sensitive evidence, use the repository's private reporting channel and redact unnecessary details.

The application must use a Supabase anon or publishable key only. Never place a Supabase service-role key in Streamlit secrets, source code, browser storage, logs, or deployment output.
