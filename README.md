# Lab Project Dashboard

A **fully self-hosted, zero-subscription** dashboard for a healthcare-AI research lab.
No Airtable, no Railway, no SaaS — just GitHub repos, GitHub Actions, and a static
site. Built to demo today and to drop onto an internal VPN-hosted server later
with no code changes.

---

## How it works (plain English)

Every project lives in its own GitHub repo and describes itself in a single
`project.yaml` file. When someone edits that file and pushes, a GitHub Action
copies the project's info into one central repo (`lab-dashboard`), which is
published as a static website. The website reads a single JSON file and renders
a card for every project.

```
edit proj-xyz/project.yaml  ──push──▶  GitHub Action (in the project repo)
                                              │ runs scripts/aggregate.py
                                              ▼
                              lab-dashboard/data/projects.json   (the "database")
                                              │ commit + push
                                              ▼
                              GitHub Action (pages.yml) deploys the static site
                                              ▼
                       dashboard/  ──fetches──▶  data/projects.json  ──renders──▶ cards
```

Nothing runs continuously. There's no server to babysit. The "database" is a
plain JSON file in git, so every change is versioned and auditable.

### What's in this repo

| Path | What it is |
|------|-----------|
| `data/projects.json` | The database — auto-updated by the aggregator. Don't hand-edit. |
| `dashboard/` | The static site: `index.html`, `style.css`, `app.js`. No build step, no CDN. |
| `scripts/aggregate.py` | Upserts one `project.yaml` into `projects.json`. stdlib + pyyaml only. |
| `scripts/slack_digest.py` | Optional weekly Slack summary. stdlib only. Off by default. |
| `template/` | Copy this into a new project repo to onboard it. |
| `.github/workflows/pages.yml` | Deploys `dashboard/` (+ data) to GitHub Pages. |
| `.github/workflows/slack-digest.yml` | Scheduled digest, **disabled** until you remove `if: false`. |

---

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
needed_skills:               # e.g. [NLP, clinical data, statistics]
slack_channel:               # e.g. project-sepsis (optional)
github_repo:                 # e.g. Amsel11/proj-demo-sepsis (auto-filled by the Action)
```

The aggregator also computes two fields automatically:
- `last_updated` — timestamp of the last sync
- `deadline_soon` — `true` when the deadline is within 30 days **and** status is `active` or `writing`

---

## One-time setup

### 1. Create the dashboard repo

Push this `lab-dashboard/` folder to GitHub as a repo named **`lab-dashboard`**
(e.g. `github.com/Amsel11/lab-dashboard`). It can be public (required for free
GitHub Pages on personal accounts) or private (Pages works on private repos for
Pro/Org plans).

### 2. Create a Personal Access Token (PAT)

The project-repo Actions need permission to push into `lab-dashboard`.

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Repository access:** only select repositories → `lab-dashboard`.
3. **Permissions:** *Contents → Read and write*.
4. Generate and copy the token (starts with `github_pat_…`).

> A classic token with the `repo` scope also works if you prefer.

### 3. Add the token as a secret in each project repo

In **every project repo** (not the dashboard repo):
**Settings → Secrets and variables → Actions → New repository secret**
- Name: `DASHBOARD_TOKEN`
- Value: the PAT from step 2.

### 4. Enable GitHub Pages on `lab-dashboard`

1. `lab-dashboard` → **Settings → Pages**.
2. **Source:** *GitHub Actions* (not "Deploy from a branch").
3. Push to `main` once — `pages.yml` runs and prints the published URL
   (e.g. `https://Amsel11.github.io/lab-dashboard/`).

That URL is your live dashboard. Bookmark it.

---

## Onboard a new project (the 30-second version)

1. In the new project repo, copy the contents of this repo's `template/` folder
   to the repo root:
   ```
   project.yaml
   .github/workflows/sync-dashboard.yml
   ```
2. Fill in `project.yaml`.
3. In `.github/workflows/sync-dashboard.yml`, set the `repository:` line to your
   dashboard repo (e.g. `Amsel11/lab-dashboard`).
4. Add the `DASHBOARD_TOKEN` secret to the repo (see step 3 above).
5. Commit and push. Within ~30 seconds the card appears on the dashboard.

That's it. From then on, every edit to `project.yaml` updates the card
automatically.

---

## Test locally (no GitHub needed)

Run the aggregator against a `project.yaml` with the `--local` flag:

```bash
cd lab-dashboard
python3 -m venv .venv && source .venv/bin/activate
pip install pyyaml

python scripts/aggregate.py --local \
  --file ../proj-demo-sepsis/project.yaml \
  --repo Amsel11/proj-demo-sepsis
```

This upserts into `data/projects.json` exactly like the Action does.

**Preview the site locally** (the page uses `fetch`, which browsers block on
`file://`, so serve it over HTTP):

```bash
# from the lab-dashboard folder, mimic the Pages layout:
mkdir -p _site/data && cp -R dashboard/. _site/ && cp data/projects.json _site/data/
cd _site && python3 -m http.server 8000
# open http://localhost:8000
```

> The `app.js` loader tries `data/projects.json`, then `../data/projects.json`,
> then `projects.json`, so it works whether the site is served from the repo
> root, from `dashboard/` with a sibling `data/`, or with the JSON copied in.

---

## Optional: weekly Slack digest

`scripts/slack_digest.py` posts a grouped summary (by status, with deadline and
"open to collaborators" highlights) to a Slack Incoming Webhook. It's **off by
default**:

1. Create an Incoming Webhook in Slack and copy the URL.
2. Add it as a repo secret named `SLACK_WEBHOOK_URL`.
3. Open `.github/workflows/slack-digest.yml` and **delete the `if: false` line**.

It runs Mondays 09:00 UTC. Without `SLACK_WEBHOOK_URL` the script exits silently,
so there's no risk in leaving it wired up.

---

## Future hosting (moving off GitHub)

The `dashboard/` folder is a **fully static site with zero external
dependencies** — no CDN, no fonts, no frameworks. To host it anywhere:

- **Internal VPN server (nginx):** copy `dashboard/` and `data/projects.json`
  to the server so the page can reach `data/projects.json`, then point an nginx
  `location` at that directory. Works fully offline.
- **Quick-and-dirty:** `cd` into a folder containing `index.html` + `data/` and
  run `python3 -m http.server`. Done.
- **AWS:** drop the same files in an S3 bucket behind CloudFront (or just S3
  static hosting). No build step.

**Self-hosting the whole pipeline (no GitHub Actions):** the aggregator is a
plain function. To replace GitHub Actions with your own server, wrap
`aggregate.py` in a small FastAPI webhook receiver: on a push webhook (or a
form/API call) it reads the YAML, calls the same upsert logic, and writes
`projects.json`. The dashboard doesn't change at all — only the *trigger* does.
No frontend code changes, no schema changes.

---

## Design constraints honored

- Zero external services or subscriptions — only GitHub.
- No npm, no Node, no build step — open `index.html` (over HTTP) and it works.
- No external CDN in the frontend — runs offline behind a VPN.
- Aggregator uses Python stdlib + pyyaml only.
- The "database" is a versioned JSON file in git.
