#!/usr/bin/env python3
"""Pull model: scan an owner's repos for project.yaml and rebuild projects.json.

Run by the dashboard's OWN GitHub Action (and locally for testing). A project
repo needs nothing but a root `project.yaml` — no workflow, no secret. The
dashboard does all the work with a single token.

Discovery (config/sources.yaml):
  - explicit `repos:` list wins if set;
  - otherwise every repo under `owner:` is scanned, and any that has a root
    project.yaml is included (optionally filtered by `repo_prefix`).

Modes:
  python scripts/pull.py                  # API mode (needs $GITHUB_TOKEN)
  python scripts/pull.py --local ../..    # scan sibling folders on disk (no token)

Dependencies: Python standard library + pyyaml.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

import aggregate  # reuse normalize() / save_projects() / DEFAULT_DATA

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = REPO_ROOT / "config" / "sources.yaml"
API = "https://api.github.com"


def log(msg: str) -> None:
    print(f"[pull] {msg}", file=sys.stderr)


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------
def gh_get_json(url: str, token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "lab-dashboard-pull",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def authenticated_login(token: str) -> str | None:
    try:
        return gh_get_json(f"{API}/user", token).get("login")
    except urllib.error.HTTPError as exc:
        log(f"could not resolve token user ({exc.code}); assuming org/user listing.")
        return None


def list_owner_repos(owner: str, token: str, include_private: bool) -> list[str]:
    """Return ['owner/name', ...] for repos under `owner`."""
    login = authenticated_login(token)
    if login and owner.lower() == login.lower():
        base = f"{API}/user/repos?per_page=100&affiliation=owner"
    else:
        base = f"{API}/orgs/{owner}/repos?per_page=100"

    names: list[str] = []
    page = 1
    while True:
        url = f"{base}&page={page}"
        try:
            data = gh_get_json(url, token)
        except urllib.error.HTTPError as exc:
            # Not an org? Fall back to the public user-repos endpoint.
            if base.startswith(f"{API}/orgs/") and exc.code == 404:
                base = f"{API}/users/{owner}/repos?per_page=100"
                page = 1
                continue
            raise
        if not data:
            break
        for r in data:
            if r.get("private") and not include_private:
                continue
            names.append(r["full_name"])
        if len(data) < 100:
            break
        page += 1
    return names


def fetch_project_yaml(full_name: str, token: str) -> str | None:
    """Return the text of project.yaml from a repo's default branch, or None."""
    url = f"{API}/repos/{full_name}/contents/project.yaml"
    try:
        data = gh_get_json(url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if data.get("encoding") == "base64":
        return base64.b64decode(data.get("content", "")).decode("utf-8")
    return data.get("content", "")


# ---------------------------------------------------------------------------
# Build projects from YAML text
# ---------------------------------------------------------------------------
def record_from_yaml(text: str, repo_full: str, now: datetime) -> dict | None:
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        log(f"skip {repo_full}: invalid yaml ({exc})")
        return None
    if not isinstance(raw, dict):
        log(f"skip {repo_full}: project.yaml is not a mapping")
        return None
    return aggregate.normalize(raw, repo_full, now)


def collect_via_api(cfg: dict, now: datetime) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("DASHBOARD_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN (a PAT with read access to the project repos).")

    explicit = cfg.get("repos") or []
    if explicit:
        targets = [str(r).strip() for r in explicit if str(r).strip()]
    else:
        owner = cfg.get("owner") or os.environ.get("GITHUB_REPOSITORY_OWNER")
        if not owner:
            raise SystemExit("config 'owner' not set and GITHUB_REPOSITORY_OWNER missing.")
        include_private = bool(cfg.get("include_private", True))
        prefix = (cfg.get("repo_prefix") or "").strip()
        targets = [
            full for full in list_owner_repos(owner, token, include_private)
            if not prefix or full.split("/", 1)[1].startswith(prefix)
        ]

    projects: list[dict] = []
    for full in targets:
        text = fetch_project_yaml(full, token)
        if text is None:
            continue
        rec = record_from_yaml(text, full, now)
        if rec:
            projects.append(rec)
            log(f"pulled {full}")
    return projects


def collect_local(root: Path, cfg: dict, now: datetime) -> list[dict]:
    owner = cfg.get("owner") or "local"
    projects: list[dict] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        f = child / "project.yaml"
        if not f.is_file():
            continue
        rec = record_from_yaml(f.read_text(encoding="utf-8"), f"{owner}/{child.name}", now)
        if rec:
            projects.append(rec)
            log(f"pulled (local) {child.name}")
    return projects


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rebuild projects.json by pulling project.yaml files")
    parser.add_argument("--local", metavar="ROOT",
                        help="Scan sibling folders under ROOT instead of calling the API")
    args = parser.parse_args(argv)

    cfg = load_config()
    now = datetime.now(timezone.utc)

    if args.local:
        projects = collect_local(Path(args.local), cfg, now)
    else:
        projects = collect_via_api(cfg, now)

    projects.sort(key=lambda p: (p.get("name") or "").lower())

    # Safety: don't wipe an existing board if a transient error found nothing.
    if not projects and aggregate.DEFAULT_DATA.is_file():
        existing = aggregate.load_projects(aggregate.DEFAULT_DATA)
        if existing:
            log(f"found 0 projects but {len(existing)} already on the board; keeping existing (not overwriting).")
            return 0

    aggregate.save_projects(aggregate.DEFAULT_DATA, projects)
    log(f"rebuilt {aggregate.DEFAULT_DATA} with {len(projects)} project(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
