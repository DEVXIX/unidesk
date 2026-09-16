"""Create a GitHub Release for the current version and upload the installer.

    python tools/publish_release.py --notes "What changed"

Token: $GITHUB_TOKEN, or the GitHub login git already stores (the same one
`git push` uses). Tags and pushes vX.Y.Z first if the tag doesn't exist yet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "DEVXIX/unidesk"


def git(*args: str, input: bytes | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, input=input, capture_output=True)
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.decode().strip()}")
    return result.stdout.decode()


def token() -> str:
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    out = git("credential", "fill", input=b"protocol=https\nhost=github.com\n\n")
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("No GitHub credentials: set GITHUB_TOKEN or run `git push` once to sign in.")


def api(method: str, url: str, auth: str, body: bytes | None = None, content_type: str = "application/json"):
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {auth}", "Accept": "application/vnd.github+json",
        "User-Agent": "unidesk-release", "Content-Type": content_type,
    })
    try:
        with urllib.request.urlopen(req, timeout=600) as res:
            return json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GitHub {method} {url.split('?')[0]} -> {e.code}: {e.read().decode()[:300]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    version = re.search(r'__version__ = "(.+?)"', (ROOT / "unidesk" / "__init__.py").read_text(encoding="utf-8")).group(1)
    tag = f"v{version}"
    setup = ROOT / "dist" / f"unidesk-setup-{version}.exe"
    if not setup.exists():
        raise SystemExit(f"{setup.name} not found: run tools\\build.ps1 first")
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit your changes first (git status is not clean).")

    auth = token()
    if not git("tag", "--list", tag).strip():
        git("tag", "-a", tag, "-m", f"unidesk {version}")
    git("push", "origin", "HEAD")
    git("push", "origin", tag)

    release = api("POST", f"https://api.github.com/repos/{REPO}/releases", auth, json.dumps({
        "tag_name": tag, "name": f"unidesk {version}", "body": args.notes or f"unidesk {version}",
        "draft": False, "prerelease": False,
    }).encode())
    print(f"uploading {setup.name} ({setup.stat().st_size / 2**20:.1f} MB)...")
    api("POST", f"https://uploads.github.com/repos/{REPO}/releases/{release['id']}/assets?name={setup.name}",
        auth, setup.read_bytes(), "application/octet-stream")
    print(f"done: {release['html_url']}")


if __name__ == "__main__":
    sys.exit(main())
