# Lab Project Dashboard

A **fully self-hosted, zero-subscription** dashboard for a healthcare-AI research
lab. No Airtable, no Railway, no SaaS — just GitHub repos and a static site.
Built to demo today and to drop onto an internal VPN-hosted server later with no
code changes.

## How it works (pull model)

Every project lives in its **own** GitHub repo and describes itself in a single
`project.yaml` file at the repo root. That's the *only* thing a project repo
needs — no workflow, no secret. The central `lab-dashboard` repo periodically
scans your account (or lab org), pulls every `project.yaml` it finds, and
rebuilds one JSON file that a static website renders as cards.

```
your project repos                    lab-dashboard (this repo)
─────────────────                     ─────────────────────────
proj-sepsis/project.yaml  ┐           scripts/pull.py  (runs on a schedule
proj-agent/project.yaml   ├──scan──▶   + on demand): fetches each project.yaml,
proj-xyz/project.yaml     ┘            rebuilds data/projects.json, commits it
                                                    │
                                                    ▼
                                       pages.yml deploys the static site
                                                    │
                              dashboard/ ──fetch──▶ data/projects.json ──▶ cards
```

Nothing runs continuously, there's no server to babysit, and **projects do not
live inside the dashboard** — they're independent repos. The dashboard just
reads from them.

### What's in this repo

| Path | What it is |
|------|-----------|
| `config/sources.yaml` | Which repos/owner to scan for `project.yaml`. |
| `scripts/pull.py` | Scans repos, rebuilds `data/projects.json`. stdlib + pyyaml. |
| `scripts/aggregate.py` | Single-file upsert helper + the normalize logic `pull.py` reuses. |
| `scripts/slack_digest.py` | Optional weekly Slack summary. stdlib only. Off by default. |
| `data/projects.json` | The generated board — rebuilt by `pull.py`. Don't hand-edit. |
| `dashboard/` | The static site: `index.html`, `style.css`, `app.js`. No build, no CDN. |
| `template/project.yaml` | Copy this into any repo to make it a project. |
| `.github/workflows/pull.yml` | Scheduled/on-demand pull + commit. |
| `.github/workflows/pages.yml` | Deploys `dashboard/` (+ data) to GitHub Pages. |
| `.github/workflows/slack-digest.yml` | Scheduled digest, **disabled** until you remove `if: false`. |

## The `project.yaml` schema

```yaml
name:                        # required, human readable
status: active               # active | writing | submitted | published | paused
description:
contributors:
  -
venue:                       # e.g. NeurIPS 2026, Nature Medicine
deadline:                    # YYYY-MM-DD (quote it, e.g. '2026-09-01')
grant:                       # funding source / grant (optional)
collaboration:               # collaboration or consortium (optional)
open_to_collaborators: false
help:                        # optional header chip override: open | closed | urgent
needed_skills:               # e.g. [NLP, clinical data, statistics]
slack_channel:               # e.g. project-sepsis (optional)
github_repo:                 # filled in automatically from the repo it's pulled from
```

Two fields are computed automatically: `last_updated` and `deadline_soon`
(`true` when the deadline is within 30 days and status is `active`/`writing`).
Empty optional fields (grant, collaboration, venue…) simply don't render.

## One-time setup

### 1. Push this repo and enable Pages
Push `lab-dashboard/` to GitHub as a **public** repo (free Pages needs public).
Then **Settings → Pages → Source: GitHub Actions**. The first run gives you
`https://<owner>.github.io/lab-dashboard/`.

### 2. Add ONE token to THIS repo
The puller needs read access to your project repos (incl. private) and write
access to push the refreshed board.

1. Create a token (classic, scope **`repo`**) at
   <https://github.com/settings/tokens/new>.
2. In **this** repo: **Settings → Secrets and variables → Actions → New
   repository secret** → name **`DASHBOARD_TOKEN`**, value = the token.

That's the only secret in the whole system, and it lives only here.

### 3. Point it at your repos
Edit `config/sources.yaml`:
```yaml
owner: your-username-or-org   # who to scan
include_private: true
repo_prefix: ""               # optional; e.g. "proj-" to limit the scan
repos: []                     # optional explicit list across accounts/orgs
```

That's it. The `pull.yml` workflow runs every 30 minutes, on demand
(**Actions → Pull projects → Run workflow**), and whenever you edit the config.

## Onboard a new project (the actual 10-second version)

1. Add a `project.yaml` (copy `template/project.yaml`) to the **root** of the
   project's repo. Fill it in. Commit.
2. …that's the whole thing. The next pull picks it up, or trigger it now from
   **Actions → Pull projects → Run workflow**.

No workflow file, no secret, nothing to configure in the project repo. Remove
the `project.yaml` (or the repo) and it drops off the board on the next pull.

## Test locally (no GitHub, no token)

```bash
cd lab-dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install pyyaml

# scan sibling folders on disk for project.yaml and rebuild the board:
python scripts/pull.py --local ..
```

**Preview the site** (browsers block `fetch` on `file://`, so serve over HTTP):
```bash
mkdir -p _site/data && cp -R dashboard/. _site/ && cp data/projects.json _site/data/
cd _site && python3 -m http.server 8000   # open http://localhost:8000
```

To test the real API path locally, set a token and run without `--local`:
```bash
GITHUB_TOKEN=ghp_xxx python scripts/pull.py
```

## Optional: weekly Slack digest

`scripts/slack_digest.py` posts a grouped summary to a Slack Incoming Webhook.
Off by default: add a `SLACK_WEBHOOK_URL` secret and delete the `if: false`
line in `.github/workflows/slack-digest.yml`. Runs Mondays 09:00 UTC.

## Future hosting (moving off GitHub)

The `dashboard/` folder is a **fully static site with zero external
dependencies** — no CDN, no fonts, no frameworks.

- **Internal VPN server (nginx):** copy `dashboard/` + `data/projects.json` to
  the server, point nginx at it. Works fully offline.
- **Quick-and-dirty:** `python3 -m http.server` from a folder with `index.html`
  + `data/`.
- **AWS:** drop the files in S3 behind CloudFront. No build step.

**Self-hosting the pull pipeline:** `pull.py` is plain Python — run it from cron
or a tiny FastAPI endpoint on your own box instead of GitHub Actions. It writes
the same `projects.json`; the dashboard doesn't change at all. Only the trigger
moves.

## Design constraints honored

- Zero external services or subscriptions — only GitHub.
- One secret total, in one repo. Project repos need only a `project.yaml`.
- No npm/Node/build step; no CDN in the frontend (runs offline behind a VPN).
- Python stdlib + pyyaml only. The board is a versioned JSON file in git.
