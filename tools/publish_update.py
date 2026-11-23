"""Publish the verified installer and manifest to GitHub Releases.

Uses the publisher's Git credential manager; credentials never enter the EXE.
Existing stable releases are never overwritten.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.version import APP_VERSION
from core.update_source import UPDATE_MANIFEST_URL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notes-file', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    prefix = "https://github.com/"
    suffix = "/releases/latest/download/latest.json"
    if not UPDATE_MANIFEST_URL.startswith(prefix) or not UPDATE_MANIFEST_URL.endswith(suffix):
        raise SystemExit("Configure a GitHub Releases update source before publishing.")
    repo = UPDATE_MANIFEST_URL[len(prefix):-len(suffix)]
    manifest_path = root / "dist/update/latest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    installer = root / "dist" / f"AutoMuseAI_Setup_v{APP_VERSION}.exe"
    digest = hashlib.sha256()
    with installer.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    expected_url = f"https://github.com/{repo}/releases/download/v{APP_VERSION}/{installer.name}"
    if (manifest.get("version") != APP_VERSION or manifest.get("installer_url") != expected_url
            or manifest.get("size") != installer.stat().st_size
            or manifest.get("sha256") != digest.hexdigest()):
        raise SystemExit("Manifest does not match installer. Run prepare_update.py again.")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    credential = subprocess.run(["git", "credential", "fill"],
                                input="protocol=https\nhost=github.com\n\n", text=True,
                                capture_output=True, env=env)
    values = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    token = os.environ.get("GITHUB_TOKEN") or values.get("password")
    if not token:
        raise SystemExit("Sign in to GitHub on the publisher machine first.")
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}",
                            "Accept": "application/vnd.github+json",
                            "User-Agent": "AutoMuseAI-Publisher"})
    api = f"https://api.github.com/repos/{repo}/releases"

    def checked(response):
        if not response.ok:
            raise SystemExit(f"GitHub request failed (HTTP {response.status_code}); no credentials logged.")
        return response.json()

    existing = session.get(f"{api}/tags/v{APP_VERSION}", timeout=30)
    if existing.status_code == 200:
        release = checked(existing)
        if not release.get("draft"):
            raise SystemExit("This version is already published. Increase the version before publishing.")
    elif existing.status_code == 404:
        release = checked(session.post(api, json={
            "tag_name": f"v{APP_VERSION}", "name": f"AutoMuseAI Studio v{APP_VERSION}",
            "draft": True, "prerelease": False,
            "body": args.notes_file.read_text(encoding='utf-8') if args.notes_file else
                    "Bộ cài Windows đầy đủ. Hỗ trợ cập nhật trong ứng dụng, giữ cấu hình và profile.\n"
                    "Người dùng bản cũ chưa có nguồn cập nhật cần cài đè bộ cài này một lần."
        }, timeout=30))
    else:
        checked(existing)
    upload_url = release["upload_url"].split("{")[0]
    for file in (installer, manifest_path):
        # A retry can replace incomplete assets on our unpublished draft only.
        for asset in release.get("assets", []):
            if asset["name"] == file.name:
                response = session.delete(asset["url"], timeout=30)
                if response.status_code != 204:
                    raise SystemExit(f"Cannot replace draft asset (HTTP {response.status_code}).")
        with file.open("rb") as stream:
            asset = checked(session.post(upload_url, params={"name": file.name}, data=stream,
                                         headers={"Content-Type": "application/octet-stream"}, timeout=(30, 900)))
        if asset.get("size") != file.stat().st_size or asset.get("state") != "uploaded":
            raise SystemExit("Upload incomplete; release remains a draft.")
        print(f"Uploaded {file.name} ({file.stat().st_size} bytes)", flush=True)
    published = checked(session.patch(f"{api}/{release['id']}",
                                      json={"draft": False, "make_latest": "true"}, timeout=30))
    print(f"Published: {published['html_url']}")


if __name__ == "__main__":
    main()
