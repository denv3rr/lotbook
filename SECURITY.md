# Security Policy

This is a local-first research application. It is not a certified government
system and does not claim FedRAMP, DoD, or formal pentest accreditation.

## Supported versions

Security fixes land on the default `main` branch.

## Reporting a vulnerability

Do not open a public issue for an exploitable defect.

1. Use GitHub Security Advisories for this repository, or
2. Contact the repository owner through GitHub.

Include the affected path, a minimal reproduction, and the impact. We will
acknowledge the report and track the fix on a private advisory until a patch
is on `main`.

## What this repo already requires

- No secrets, `.env` files, databases, or local runtime data in git
- API key auth when `LOTBOOK_WEB_API_KEY` is set
- Destructive maintenance routes require an explicit confirm payload
- Dependency alerts are handled through Dependabot

## Local verification

```pwsh
python -m pytest tests/test_security.py
```

That suite is defensive and isolated. It does not attack remote systems.
