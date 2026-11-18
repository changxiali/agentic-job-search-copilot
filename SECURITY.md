# Security Policy

## Secrets and personal data

Never commit `.env`, API keys, email authorization codes, Feishu secrets, resumes,
mailboxes, logs, SQLite databases, Candidate Profiles, job records or interview data.
Use only `.env.example` and the fictional files ending in `.example.*` as templates.

If a credential is committed accidentally, revoke and rotate it immediately. Removing
it from the latest commit is not sufficient because it can remain in Git history.

## Reporting a vulnerability

Please open a GitHub Security Advisory instead of publishing credentials or exploitable
details in a public issue.

