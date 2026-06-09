#!/usr/bin/env python3
"""Optional weekly Slack digest.

Reads data/projects.json and posts a formatted summary to a Slack Incoming
Webhook. Does nothing (exits 0) unless SLACK_WEBHOOK_URL is set, so it is safe
to leave wired up.

Dependencies: Python standard library only (no pyyaml, no requests).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_PATH = REPO_ROOT / "data" / "projects.json"

STATUS_ORDER = ["active", "writing", "submitted", "published", "paused"]
STATUS_EMOJI = {
    "active": ":large_blue_circle:",
    "writing": ":large_yellow_circle:",
    "submitted": ":large_purple_circle:",
    "published": ":large_green_circle:",
    "paused": ":white_circle:",
}


def load_projects() -> list[dict]:
    if not DATA_PATH.is_file():
        return []
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def build_message(projects: list[dict]) -> str:
    if not projects:
        return ":bar_chart: *Weekly lab digest*\n\nNo projects tracked yet."

    lines = [":bar_chart: *Weekly lab digest*", ""]

    # Group by status.
    by_status: dict[str, list[dict]] = {}
    for p in projects:
        by_status.setdefault((p.get("status") or "active"), []).append(p)

    for status in STATUS_ORDER:
        group = by_status.get(status)
        if not group:
            continue
        emoji = STATUS_EMOJI.get(status, ":white_circle:")
        lines.append(f"{emoji} *{status.capitalize()}* ({len(group)})")
        for p in sorted(group, key=lambda x: (x.get("name") or "").lower()):
            name = p.get("name", "Untitled")
            venue = p.get("venue")
            deadline = p.get("deadline")
            suffix = ""
            if venue and deadline:
                suffix = f" — {venue}, due {deadline}"
            elif venue:
                suffix = f" — {venue}"
            elif deadline:
                suffix = f" — due {deadline}"
            lines.append(f"   • {name}{suffix}")
        lines.append("")

    # Deadlines soon.
    soon = [p for p in projects if p.get("deadline_soon")]
    if soon:
        lines.append(":rotating_light: *Deadlines within 30 days*")
        for p in sorted(soon, key=lambda x: x.get("deadline") or ""):
            lines.append(f"   • {p.get('name')} — {p.get('venue') or 'deadline'} on {p.get('deadline')}")
        lines.append("")

    # Open to collaborators.
    open_projects = [p for p in projects if p.get("open_to_collaborators")]
    if open_projects:
        lines.append(":handshake: *Open to collaborators*")
        for p in sorted(open_projects, key=lambda x: (x.get("name") or "").lower()):
            skills = ", ".join(p.get("needed_skills") or [])
            tail = f" — needs: {skills}" if skills else ""
            lines.append(f"   • {p.get('name')}{tail}")
        lines.append("")

    return "\n".join(lines).rstrip()


def post_to_slack(webhook_url: str, text: str) -> None:
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", "replace")
        if resp.status >= 300 or body.strip() not in ("ok", ""):
            raise RuntimeError(f"Slack responded {resp.status}: {body}")


def main() -> int:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL not set; skipping digest.", file=sys.stderr)
        return 0

    message = build_message(load_projects())
    try:
        post_to_slack(webhook, message)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Failed to post digest: {exc}", file=sys.stderr)
        return 1
    print("Digest posted to Slack.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
