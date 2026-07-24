# Security

## Reporting issues

If you find a security issue in this repository (including accidental secret exposure), open a private report with the repository owner if possible. **Do not post live API keys, tokens, or passwords in public issues.**

## Secrets and personal config

| Item | Where it belongs | Committed? |
|------|------------------|------------|
| Databricks PAT / OAuth | `databricks auth login` → `~/.databrickscfg` | Never |
| CLI profile name, email, warehouse ID | Local `.env` | Never (use `.env.example`) |
| The Odds API key | `.env` + Databricks secret scope `nfl` / `odds_api_key` | Never |
| Workspace host / Genie space IDs | `.env` / `.databricks/` (via `sync_bundle_env.py`) | Never |
| Live odds dumps | `staging/odds_latest.json` | Never |

## Public-ready check

Before pushing:

```bash
python scripts/check_public_ready.py
```

CI runs the same check. It fails if tracked files contain real workspace hosts, personal absolute paths, forbidden paths (`.env`, live odds JSON), or secret-like literals.

## After a leak

1. **Rotate** the credential immediately (Odds API key, Databricks token, etc.).
2. Remove it from the working tree and ensure it is gitignored.
3. If it was committed, scrub history (`git filter-repo` or BFG) and force-push only if you understand the impact; still rotate the secret either way.
4. Enable GitHub **secret scanning** and **push protection** on the repository.
