# bd2-ws-watcher

Watches Weiss Schwarz product news and store stock, with a focus on Brown Dust 2 sealed product. Alerts go out through Discord and email, and a dashboard runs on the local network. It is one Python Docker container with a SQLite database.

The spec is `.scratch/bd2-watcher/spec.md`. Read `GLOSSARY.md` before naming anything.

## Rules

- Never commit secrets. Webhook URLs, the Gmail app password and the like live in `.env`, which is gitignored.
- Tests never hit live sites. They run against saved fixtures in `tests/fixtures/`.
- Be polite to the sites we check: identify ourselves with a User-Agent, respect robots.txt, and never poll faster than the configured intervals.
- Don't use em-dashes in prose.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
