---
title: Login Troubleshooting
doc_type: runbook
product_area: auth
updated_at: 2026-04-15
---

# Login Troubleshooting

## Common Causes
Login issues are commonly caused by expired sessions, incorrect passwords, locked accounts, browser cache problems, or multi-factor authentication failures.

## Recommended Steps
Ask the customer to reset their password, clear browser cache, try an incognito window, and confirm they are using the correct email address. If logs show AUTH_TOKEN_EXPIRED, advise the customer to sign out fully and sign in again.

## Escalation
Escalate to Identity Engineering if logs show repeated MFA failures, account lock state cannot be cleared, or multiple customers report the same authentication error.
