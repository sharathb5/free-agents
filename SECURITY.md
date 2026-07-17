# Security Policy

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

We use GitHub's private vulnerability reporting. To report a security issue:

1. Go to the [Security tab](https://github.com/sharathb5/free-agents/security) of this repository.
2. Click **"Report a vulnerability"** (requires a GitHub account).
3. Fill in the details — steps to reproduce, impact, and any suggested fix.

We will acknowledge receipt within **72 hours** and aim to provide a fix or mitigation within **14 days** for confirmed critical issues.

## Scope

Issues we consider in scope:

- Authentication bypass (Clerk JWT verification, `AUTH_TOKEN` handling)
- Remote code execution or arbitrary command injection
- Secrets leaking through API responses or logs
- CORS misconfigurations that allow cross-origin data access
- SQL/NoSQL injection in database-backed routes

Out of scope:

- Vulnerabilities in third-party dependencies (report those upstream)
- Social engineering, phishing
- Denial-of-service against self-hosted deployments

## Supported Versions

We support the latest published version on PyPI (`agent-toolbox`). Older versions do not receive security patches.

## Disclosure Policy

We follow coordinated disclosure. Please give us reasonable time to patch before any public disclosure.
