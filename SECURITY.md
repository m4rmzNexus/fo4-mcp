# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for an
unfixed vulnerability.

- Preferred: GitHub's **private vulnerability reporting** (the "Report a
  vulnerability" button under this repository's **Security** tab).
- Alternatively, contact the maintainer through their GitHub profile.

Please include a description, reproduction steps, and impact. Do **not** include
any secrets (API keys, tokens) in your report.

## Scope notes

fo4-mcp is a local developer tool that shells out to a Fallout 4 modding
toolchain. A few things worth knowing:

- **Secrets** live in `secrets/` (e.g. a Nexus API key), which is **gitignored
  and never committed**. If you ever find a secret in the git history or a
  tracked file, treat it as a vulnerability and report it.
- **Subprocess boundary.** Third-party tools are invoked as out-of-process
  subprocesses (`subprocess_wrap.run_tool()`). Reports about command
  construction / argument injection into these calls are in scope.
- **Write boundary.** The server enforces a safe-write policy
  (`mcp-server/fo4_mcp/safety.py`) that denies writes to the game install and
  user data dirs. A bypass of that boundary is in scope.

## Supported versions

This is pre-1.0 software; only the latest `main` is supported.
