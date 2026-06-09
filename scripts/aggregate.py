#!/usr/bin/env python3
"""Aggregator: upsert a single project.yaml into data/projects.json.

Called by the GitHub Action with the project YAML content and repo name passed
as environment variables (PROJECT_YAML and GITHUB_REPO). Can also be run
locally for testing:

    python scripts/aggregate.py --local \
        --file ../proj-demo-sepsis/project.yaml \
        --repo Amsel11/proj-demo-sepsis

Dependencies: Python standard library + pyyaml only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

# Resolve data/projects.json relative to this script's repo, so the default
# works both locally and when the dashboard repo is checked out by the Action.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_DATA = REPO_ROOT / "data" / "projects.json"

DEADLINE_WINDOW_DAYS = 30
SOON_STATUSES = {"active", "writing"}
VALID_STATUSES = {"active", "writing", "submitted", "published", "paused"}

# Canonical field order + default values for every project record.
DEFAULTS: dict[str, object] = {
    "name": "",
    "status": "active",
    "description": "",
    "contributors": [],
    "venue": "",
    "deadline": "",
    "open_to_collaborators": False,
    "needed_skills": [],
    "slack_channel": "",
    "github_repo": "",
}


def log(message: str) -> None:
    print(f"[aggregate] {message}", file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert a project into projects.json")
    parser.add_argument("--local", action="store_true",
                        help="Local test mode (reads --file instead of $PROJECT_YAML)")
    parser.add_argument("--file", help="Path to a project.yaml (local mode)")
    parser.add_argument("--repo", help="Full repo name, e.g. Amsel11/proj-demo-sepsis")
    parser.add_argument("--data", help="Path to projects.json (defaults to repo data/)")
    return parser.parse_args(argv)


def read_yaml_text(args: argparse.Namespace) -> str:
    """Return the raw YAML text from --file or the PROJECT_YAML env var."""
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            raise SystemExit(f"--file not found: {path}")
        return path.read_text(encoding="utf-8")
    env_yaml = os.environ.get("PROJECT_YAML")
    if env_yaml:
        return env_yaml
    raise SystemExit("No project YAML provided: pass --file or set PROJECT_YAML")


def resolve_repo(args: argparse.Namespace, parsed: dict) -> str:
    """Repo name precedence: --repo > $GITHUB_REPO > yaml's github_repo."""
    repo = args.repo or os.environ.get("GITHUB_REPO") or parsed.get("github_repo")
    if not repo:
        raise SystemExit("No repo name: pass --repo or set GITHUB_REPO")
    return str(repo).strip()


def to_date(value) -> date | None:
    """Coerce a YAML date/datetime/string into a date, or None if unparseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        log(f"Unparseable deadline {value!r}; ignoring.")
        return None


def deadline_iso(value) -> str:
    d = to_date(value)
    return d.isoformat() if d else ""


def compute_deadline_soon(deadline_value, status: str, today: date) -> bool:
    d = to_date(deadline_value)
    if d is None or status not in SOON_STATUSES:
        return False
    days = (d - today).days
    return 0 <= days <= DEADLINE_WINDOW_DAYS


def normalize(raw: dict, repo: str, now: datetime) -> dict:
    """Merge a parsed yaml dict onto the defaults and add computed fields."""
    record = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw and raw[key] is not None:
            record[key] = raw[key]

    # Coerce/clean a few fields.
    record["status"] = str(record["status"]).strip().lower() or "active"
    if record["status"] not in VALID_STATUSES:
        log(f"Unknown status {record['status']!r}; leaving as-is.")
    record["contributors"] = [str(c).strip() for c in (record["contributors"] or []) if str(c).strip()]
    record["needed_skills"] = [str(s).strip() for s in (record["needed_skills"] or []) if str(s).strip()]
    record["open_to_collaborators"] = bool(record["open_to_collaborators"])
    record["deadline"] = deadline_iso(record["deadline"])

    # Computed / authoritative fields.
    record["github_repo"] = repo
    record["last_updated"] = now.isoformat(timespec="seconds")
    record["deadline_soon"] = compute_deadline_soon(record["deadline"], record["status"], now.date())
    return record


def load_projects(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"Could not read existing {path} ({exc}); starting fresh.")
        return []
    return data if isinstance(data, list) else []


def upsert(projects: list[dict], record: dict) -> list[dict]:
    """Replace the project with the same github_repo, or append it."""
    key = record["github_repo"]
    out = [p for p in projects if p.get("github_repo") != key]
    out.append(record)
    out.sort(key=lambda p: (p.get("name") or "").lower())
    return out


def save_projects(path: Path, projects: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(projects, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)

    text = read_yaml_text(args)
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"Invalid YAML: {exc}")
    if not isinstance(parsed, dict):
        raise SystemExit("project.yaml must be a mapping at the top level.")

    repo = resolve_repo(args, parsed)
    record = normalize(parsed, repo, now)

    data_path = Path(args.data) if args.data else DEFAULT_DATA
    projects = load_projects(data_path)
    projects = upsert(projects, record)
    save_projects(data_path, projects)

    log(f"Upserted {repo} -> {data_path} ({len(projects)} projects total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
